import time
from transformers import pipeline
import json
import warnings

# Suppress minor huggingface warnings for cleaner console output
warnings.filterwarnings("ignore")

result = {}

class ModernBERTScamAnalyzer:
    """Stateful context analyzer using only ModernBERT for hyper-sensitive detection."""
    def __init__(self, alpha=0.7, max_buffer_words=500):
        self.model_id = "MoritzLaurer/ModernBERT-large-zeroshot-v2.0"
        print(f"Loading {self.model_id}...")
        
        self.classifier = pipeline("zero-shot-classification", model=self.model_id)
        
        # Tuned labels to be highly sensitive to the very first line ("illegal activity")
        # as well as the progression into digital arrest.
        self.candidate_labels = [
            "illegal activity accusation",
            "digital arrest threat", 
            "financial extortion", 
            "normal safe conversation",
            "genuine law enforcement warning"
        ]
        self.scam_labels = [
            "illegal activity accusation", 
            "digital arrest threat", 
            "financial extortion"
        ]
        
        self.running_score = 0.0
        self.full_transcript_buffer = []
        self.alpha = alpha
        self.max_buffer_words = max_buffer_words

    def process_chunk(self, new_chunk_text):
        if not new_chunk_text.strip():
            return self.running_score

        # 1. Update text buffer
        self.full_transcript_buffer.append(new_chunk_text.strip())
        combined_context = " ".join(self.full_transcript_buffer)
        
        words = combined_context.split()
        if len(words) > self.max_buffer_words:
            combined_context = " ".join(words[-self.max_buffer_words:])

        result = self.classifier(combined_context, self.candidate_labels)
        
        # 3. Calculate current chunk raw probability
        current_context_risk = 0.0
        for label, score in zip(result['labels'], result['scores']):
            if label in self.scam_labels:
                current_context_risk += score

        current_risk_scaled = current_context_risk * 100
        
        if self.running_score == 0.0:
            self.running_score = current_risk_scaled
        else:
            # Latch-and-hold logic: 
            # If current risk is higher, adapt quickly.
            # If current risk drops, decay very slowly to remember the severe threat.
            if current_risk_scaled > self.running_score:
                self.running_score = (self.alpha * current_risk_scaled) + ((1 - self.alpha) * self.running_score)
            else:
                self.running_score = max(current_risk_scaled, self.running_score * 0.95)
            
        return round(self.running_score, 2), result['labels'][0]


# ==========================================
# MAIN EXECUTION 
# ==========================================
def scam_detector():
    print("\n" + "="*70)
    print("INITIALIZING MODERNBERT (Highly Sensitive Configuration)")
    print("="*70)
    
    analyzer = ModernBERTScamAnalyzer()

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

    print("\n" + "═"*90)
    print("🚨 STARTING ITERATIVE LIVE STREAM (MODERNBERT ONLY)")
    print("═"*90)

    for index, chunk in enumerate(live_call_stream, start=1):
        print(f"\n⏱️ [Time Loop +{(index * 10)}s] Incoming Chunk:\n   \"{chunk}\"")
        
        # Process the chunk and get the score and top label
        score, top_label = analyzer.process_chunk(chunk)
    
        if score > 75:
            status = "🔴 CRITICAL RISK"
        elif score > 40:
            status = "🟡 WARNING"
        else:
            status = "🟢 LOW RISK"

        result.update({
            chunk:{
            'ModernBERT Score': score,
            'Top Detected Intent': top_label,
            'status': status
            }   
        })
        
        print("-" * 50)
        print(f"   ModernBERT Score: {score} / 100")
        print(f"   Top Detected Intent: '{top_label}'")
        print(f"   ► OVERALL STATUS: {status}")
        print("═" * 90)

    return result
    
    # Brief pause to simulate network stream
    time.sleep(1)

print("\n🏁 Call Stream Finished.")