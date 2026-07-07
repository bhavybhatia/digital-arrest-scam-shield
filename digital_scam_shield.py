import time
import os
import json
import warnings
from openai import OpenAI

# Suppress minor warnings for cleaner console output
warnings.filterwarnings("ignore")


result = {}

class RouterScamAnalyzer:
    """Stateful context analyzer using Hugging Face Router API (OpenAI Compatible)."""
    def __init__(self, hf_token, alpha=0.7, max_buffer_words=500):
        # Using a fast, instruction-tuned LLM available on the HF Router
        self.model_id = "meta-llama/Meta-Llama-3-8B-Instruct" 
        
        # Initialize the standard OpenAI client but point it to Hugging Face
        self.client = OpenAI(
            base_url="https://router.huggingface.co/v1",
            api_key=hf_token
        )
        
        print(f"Configured to use HF Router API for {self.model_id}...")
        
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
                        )
                    },
                    {"role": "user", "content": f"Transcript:\n{combined_context}"}
                ],
                temperature=0.1, # Low temperature for consistent classification
            )
            
            # Parse the JSON response from the LLM
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

        # 3. Latch-and-hold logic
        if self.running_score == 0.0:
            self.running_score = current_risk_scaled
        else:
            if current_risk_scaled > self.running_score:
                self.running_score = (self.alpha * current_risk_scaled) + ((1 - self.alpha) * self.running_score)
            else:
                self.running_score = max(current_risk_scaled, self.running_score * 0.95)
            
        return round(self.running_score, 2), top_label

HF_TOKEN = "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" 
analyzer = RouterScamAnalyzer(hf_token=HF_TOKEN)


# ==========================================
# MAIN EXECUTION 
# ==========================================
def scam_detector():
    # Replace with your actual Hugging Face Access Token
    
    print("\n" + "="*70)
    print("INITIALIZING LLM (Hugging Face Router API Mode)")
    print("="*70)
    

    live_call_stream = [
        "Hello, am I speaking with Mr. Raghav Ahuja? Sir, your phone number has been linked to an illegal activity.",
        "A package containing 5 fake passports and 20 grams of MDMA has been intercepted by Customs in Mumbai.",
        "Your Aadhar card identity was used to open this logistics account. The local police are tracking you right now.",
        "We are transferring this call to the high-ranking officials at the CBI Cyber Crime Branch via a secure room link.",
        "You are now under complete Digital Arrest. Do not disconnect this line, close your doors, or talk to anyone.",
        "To clear your official government records, you must move all funds to the RBI public verification bank account immediately.",
        "Okay, fine. I am waiting for your bank transfer conformation confirmation text. Do it quickly.",
        "Hello, this is Inspector Deshmukh from the local station. We traced this call. Please disconnect immediately, this is a scam."
    ]

    # live_call_stream = [
    # # --- Phase 1: Normal & Safe Conversation ---
    # "Hello Mr. Raghav, this is Priya calling from Global Logistics. Your delivery courier is outside your gate.",
    # "Could you please confirm if there is someone available at home to collect the parcel right now?",
    # "Perfect, I will hand it over to the security guard at the main gate desk. Have a wonderful day ahead!",
    
    # # --- Phase 2: Shift to an Online Money / Job Scam ---
    # "Hello, is this Raghav? I am reaching out from Global HR Solutions regarding an exciting part-time remote work offer.",
    # "You can easily earn up to 5,000 Rupees daily simply by liking YouTube videos and completing quick social tasks from home.",
    # "To activate your employee account and release your initial sign-up bonus, please click this link to register.",
    # "To unlock premium high-paying tasks, you must send a small security deposit to our digital verification wallet immediately.",
    # "The remaining slots are filling up fast. Transfer the deposit right now and send the transaction screenshot to start earning."
    # ]

    print("\n" + "═"*90)
    print("🚨 STARTING ITERATIVE LIVE STREAM (ROUTER API MODE)")
    print("═"*90)

    for index, chunk in enumerate(live_call_stream, start=1):
        print(f"\n⏱️ [Time Loop +{(index * 10)}s] Incoming Chunk:\n   \"{chunk}\"")
        
        score, top_label = analyzer.process_chunk(chunk)

        if score > 75:
            status = "🔴 CRITICAL RISK"
        elif score > 40:
            status = "🟡 WARNING"
        else:
            status = "🟢 LOW RISK"

        result.update({
            chunk:{
                'Score': score,
                'Top Detected Intent': top_label,
                'status': status
            }   
        })
        
        print("-" * 50)
        print(f"   Risk Score: {score} / 100")
        print(f"   Top Detected Intent: '{top_label}'")
        print(f"   ► OVERALL STATUS: {status}")
        print("═" * 90)
    
        time.sleep(1)

    return result


print("\n🏁 Call Stream Finished.")