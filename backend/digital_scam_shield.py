import os
import warnings
import json

from openai import OpenAI

# Suppress minor warnings for cleaner console output
warnings.filterwarnings("ignore")


class RouterScamAnalyzer:
    """Stateful context analyzer using Hugging Face Router API (OpenAI Compatible)."""

    def __init__(self, hf_token, alpha=0.7, max_buffer_words=500):
        # Using a fast, instruction-tuned LLM available on the HF Router
        self.model_id = "meta-llama/Llama-3.1-8B-Instruct"

        # Initialize the standard OpenAI client but point it to Hugging Face
        self.client = OpenAI(
            base_url="https://router.huggingface.co/v1",
            api_key=hf_token,
        )

        self.running_score = 0.0
        self.full_transcript_buffer = []
        self.alpha = alpha
        self.max_buffer_words = max_buffer_words

    def process_chunk(self, new_chunk_text):
        if not new_chunk_text.strip():
            return self.running_score, "None"

        # 1. Update text buffer
        self.full_transcript_buffer.append(new_chunk_text.strip())
        combined_context = " ".join(self.full_transcript_buffer)

        words = combined_context.split()
        if len(words) > self.max_buffer_words:
            combined_context = " ".join(words[-self.max_buffer_words:])

        # 2. Call the Router API
        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a Scam Detection API. Analyze the conversation transcript and output strictly a JSON object with two keys: "
                            "'intent' (choose exactly one of: 'illegal activity accusation', 'digital arrest threat', 'financial extortion', 'genuine law enforcement warning', 'normal safe conversation') "
                            "and 'scam_probability' (a float between 0.0 and 1.0 representing the likelihood this is a scam). Do not include any other text."
                        ),
                    },
                    {"role": "user", "content": f"Transcript:\n{combined_context}"},
                ],
                temperature=0.1,  # Low temperature for consistent classification
            )

            content = response.choices[0].message.content

            # Strip markdown formatting if the LLM wraps the JSON
            if content.startswith("```json"):
                content = content.strip("```json").strip("```").strip()

            data = json.loads(content)
            top_label = data.get("intent", "unknown")
            current_risk_scaled = float(data.get("scam_probability", 0.0)) * 100

        except Exception as e:
            print(f"   [API Error] {e}")
            return self.running_score, "API_ERROR"

        # 3. Latch-and-hold logic: adapt quickly to rising risk, decay slowly
        # so a severe threat earlier in the call isn't forgotten.
        if self.running_score == 0.0:
            self.running_score = current_risk_scaled
        else:
            if current_risk_scaled > self.running_score:
                self.running_score = (self.alpha * current_risk_scaled) + ((1 - self.alpha) * self.running_score)
            else:
                self.running_score = max(current_risk_scaled, self.running_score * 0.95)

        return round(self.running_score, 2), top_label


# ==========================================
# MAIN EXECUTION
# ==========================================
_analyzer = None


def _get_analyzer():
    """Lazily create and reuse a single analyzer instance across calls,
    so the client is built once and running_score persists across chunks."""
    global _analyzer
    if _analyzer is None:
        hf_token = os.environ.get("HF_TOKEN")
        if not hf_token:
            raise RuntimeError(
                "HF_TOKEN environment variable is not set. Set it to a Hugging Face "
                "access token with Router API access before starting the server."
            )
        print(f"Configuring HF Router API scam analyzer...")
        _analyzer = RouterScamAnalyzer(hf_token=hf_token)
    return _analyzer


def preload():
    """Create the analyzer up front, mirroring scam_analyser.preload() so
    app.py can warm up either backend the same way before starting audio
    capture threads."""
    _get_analyzer()


def scam_detector(chunk):
    analyzer = _get_analyzer()

    score, top_label = analyzer.process_chunk(chunk)

    if score > 75:
        status = "\U0001F534 CRITICAL RISK"
    elif score > 40:
        status = "\U0001F7E1 WARNING"
    else:
        status = "\U0001F7E2 LOW RISK"

    print("-" * 50)
    print(f"   Risk Score: {score} / 100")
    print(f"   Top Detected Intent: '{top_label}'")
    print(f"   Overall status: {status}")

    return score, top_label, status
