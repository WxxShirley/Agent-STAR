from prompt import FORMAT_PLANNING 
import requests 
import os  
import json


DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")


def call_openai(messages: list[dict], max_retries: int = 20, model: str = "deepseek-chat") -> str: 
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}" 
    }

    # base_url = "https://api.deepseek.com/chat/completions"
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions" 

    payload = {
        "model": "deepseek-v3.2-exp",
        "messages": messages,
        "max_tokens": 8192,
    }

    while max_retries:
        try:
            response = requests.post(base_url, headers=headers, json=payload, timeout=240)
            content = response.json()["choices"][0]["message"]["content"] 
            
            if content: 
                content = content.replace("```json", "").replace("```", "").strip()
                content = json.loads(content)  
                return content 

        except Exception as e:
            # print(e)
            max_retries -= 1 
            import time 
            time.sleep(0.2)
            if max_retries == 0:
                print(f"[OpenAI] Failed to call OpenAI after {max_retries} attempts") 
                return None
    
    
def format_planning(prediction: str, query: str, model: str = "deepseek-chat") -> str: 
    if "answer not found" in prediction.lower():
      return []
    
    format_planning_prompt = FORMAT_PLANNING.replace("{{{planning_text}}}", prediction).replace("{{{user_query}}}", query)
    msgs = [{"role": "system", "content": "You are a helpful assistant that formats text into a strict JSON format."}, {"role": "user", "content": format_planning_prompt}]
    
    return call_openai(msgs, model=model) 


def format_planning_for_official_test(prediction: str, query: str, model: str = "deepseek-chat") -> str:  
    if "answer not found" in prediction.lower():
      return []
    
    format_planning_prompt = FORMAT_PLANNING.replace("{{{planning_text}}}", prediction).replace("{{{user_query}}}", query)
    msgs = [{"role": "system", "content": "You are a helpful assistant that formats text into a strict JSON format."}, {"role": "user", "content": format_planning_prompt}]
    
    json_content = call_openai(msgs, model=model) 
    # json_content = call_local(msgs)
    
    for idx, content in enumerate(json_content): 
      if "transportation" in content and content["transportation"] != "-":
        if "driving" in content["transportation"].lower() and "self-driving" not in content["transportation"].lower(): 
          transportation_str = content["transportation"].replace("driving", "Self-driving") 
          transportation_str = transportation_str.replace("Driving", "Self-driving")  
          content["transportation"] = transportation_str 
          json_content[idx] = content 
        elif "drive" in content["transportation"].lower(): 
          transportation_str = content["transportation"].replace("drive", "Self-driving") 
          transportation_str = transportation_str.replace("Drive", "Self-driving")  
          content["transportation"] = transportation_str 
          json_content[idx] = content 
        elif "car" in content["transportation"].lower(): 
          transportation_str = content["transportation"].replace("car", "Self-driving") 
          transportation_str = transportation_str.replace("Car", "Self-driving")  
          content["transportation"] = transportation_str 
          json_content[idx] = content 
        
        if content["transportation"].startswith("from"):
          transportation_str = "Self-driving, " + content["transportation"]
          content["transportation"] = transportation_str 
          json_content[idx] = content 
        if content["transportation"].startswith("Cost:"): 
          transportation_str = "Self-driving, " + content["transportation"]
          content["transportation"] = transportation_str 
          json_content[idx] = content 

    return json_content 


if __name__ == "__main__": 
    prediction = """**Comprehensive Travel Plan: Pittsburgh to Baltimore (March 4-6, 2022)**  
**Total Budget: $1,200**  

---

### **Day 1: March 4 (Arrival Day)**  
- **Flight**:  
  - [F3969954] $52, Departure 16:51, Arrival 17:49 (Pittsburgh → Baltimore).  
- **Accommodation**:  
  - [Contemporary Home Away from Home, Entire house] $290/night (Option 2).  
  - **Address**: [Check availability for March 4-6](search link).  
- **Transportation**:  
  - Taxi from BWI Airport to hotel: ~$50 (estimate).  
- **Meals**:  
  - **Lunch**: [Carmel Café](https://carmelbaltimore.com/) (Fell's Point, $20).  
  - **Dinner**: [The Wharf seafood market](https://www.thewharf.com/) (Inner Harbor, $30).  
- **Attractions**:  
  - **National Aquarium** (Free parking, $29.95 entry).  
  - **Inner Harbor**: Stroll along the waterfront, visit Harborplace.  

---

### **Day 2: March 5 (Full Day Exploration)**  
- **Accommodation**:  
  - [Contemporary Home Away from Home] $290 (2nd night).  
- **Meals**:  
  - **Breakfast**: Hotel-provided or nearby [Baltimore Coffee Roasters](https://baltimorecoffee.com/) ($10).  
  - **Lunch**: [Joe’s Seafood](https://www.joesseafood.com/) (Federal Hill, $25).  
  - **Dinner**: [Royal Prime](https://www.royalprimebaltimore.com/) (Fell's Point, $35).  
- **Attractions**:  
  - **B&O Railroad Museum** ($25 entry).  
  - **Patterson Park**: Relax in Baltimore’s oldest park.  

---

### **Day 3: March 6 (Departure Day)**  
- **Meals**:  
  - **Breakfast**: [The Halal Guy](https://www.thehalalguy.com/) (Federal Hill, $8).  
  - **Lunch**: [Woodberry Kitchen](https://www.woodberrycuisine.com/) (Woodberry, $20).  
- **Transportation**:  
  - Taxi to BWI Airport: ~$50 (estimate).  

---

### **Budget Breakdown**  
| **Category**       | **Cost**  |  
|---------------------|-----------|  
| Flights             | $52       |  
| Accommodation (2n)  | $580      |  
| Meals (3 days)      | $148      |  
| Attractions (2)     | $45       |  
| Transportation      | $100      |  
| **Total**           | **$925**  |  
**Remaining Budget**: $275 (for souvenirs, extra activities, or contingencies).  

---

### **Key Notes**  
1. **Accommodation**: Verify booking rules (e.g., no children under 10, no parties).  
2. **Transportation**: Use taxis or rideshares for airport transfers.  
3. **Attractions**: Book tickets in advance where possible (e.g., National Aquarium).  
4. **Flexibility**: Adjust meals based on preferences (all options are diverse and locally renowned).  

Enjoy Baltimore’s historic charm and vibrant food scene! 🏖️
    """

    content = format_planning(prediction, query="")
    print(content)
