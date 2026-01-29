import streamlit as st
import google.generativeai as genai
import datetime
import matplotlib.pyplot as plt
import json
import os
import boto3
from botocore.exceptions import ClientError
from decimal import Decimal
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re

# --- Page Configuration ---
st.set_page_config(page_title="Accessible Counselling Assistant", page_icon="💬", layout="wide")

# Custom CSS for chat bubbles with avatars
chat_css = """
<style>
/* Main app container for dark theme */
.stApp {
    background-color: #262730;
    color: #F0F2F6;
}

/* Make sidebar background darker */
[data-testid="stSidebar"] {
    background-color: #1F2025;
}

/* Base message container with avatar */
.chat-container {
    display: flex;
    align-items: flex-start;
    margin-bottom: 15px;
    width: 100%;
    gap: 10px;
}

/* Avatar styling */
.avatar {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    flex-shrink: 0;
    font-weight: bold;
}

.user-avatar {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    order: 2;
}

.assistant-avatar {
    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
    color: white;
    order: 1;
}

/* Base message bubble */
.chat-bubble {
    padding: 12px 16px;
    border-radius: 12px;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
    max-width: 70%;
    word-wrap: break-word;
    position: relative;
}

/* User bubble (darker blue) - aligned to the right */
.user-bubble {
    background: linear-gradient(135deg, #4a5568 0%, #2d3748 100%);
    border-radius: 12px 12px 4px 12px;
    margin-left: auto;
    order: 1;
    color: #e2e8f0;
}

/* Assistant bubble (warm gray) - aligned to the left */
.assistant-bubble {
    background: linear-gradient(135deg, #4a5568 0%, #38414a 100%);
    border-radius: 12px 12px 12px 4px;
    margin-right: auto;
    order: 2;
    color: #f7fafc;
}

/* Container for user messages (reverse order) */
.user-container {
    flex-direction: row-reverse;
}

/* Container for assistant messages (normal order) */
.assistant-container {
    flex-direction: row;
}

/* Fix avatar positioning for user */
.user-container .avatar {
    order: 1;
}

.user-container .chat-bubble {
    order: 2;
}

/* Mood indicator badge */
.mood-badge {
    position: absolute;
    top: -8px;
    right: -8px;
    background: #4CAF50;
    color: white;
    border-radius: 10px;
    padding: 2px 6px;
    font-size: 10px;
    font-weight: bold;
    min-width: 20px;
    text-align: center;
}

.mood-very-negative { background: #f44336; }
.mood-negative { background: #ff9800; }
.mood-neutral { background: #9e9e9e; }
.mood-positive { background: #4CAF50; }
.mood-very-positive { background: #8BC34A; }

/* Chat input box and buttons */
[data-testid="stChatInput"] {
    background-color: #373A47;
    border-radius: 25px;
    padding: 10px;
    border: none;
}

[data-testid="stChatInput"] input {
    color: #F0F2F6;
}

/* Crisis alert styling */
.crisis-alert {
    background: linear-gradient(135deg, #ff4444 0%, #cc0000 100%);
    color: white;
    padding: 20px;
    border-radius: 10px;
    border-left: 5px solid #ff0000;
    margin: 10px 0;
    box-shadow: 0 4px 8px rgba(255, 68, 68, 0.3);
}
</style>
"""
st.markdown(chat_css, unsafe_allow_html=True)

# --- AWS DynamoDB Configuration ---
try:
    aws_access_key_id = st.secrets["AWS_ACCESS_KEY_ID"]
    aws_secret_access_key = st.secrets["AWS_SECRET_ACCESS_KEY"]
    dynamodb = boto3.resource(
        'dynamodb',
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name="ap-southeast-1"
    )
    table = dynamodb.Table('mood_data')
    USER_ID = "user_1"
except KeyError:
    st.error("🚨 AWS credentials not found! Please add them to your Streamlit secrets.")
    st.stop()
except ClientError as e:
    st.error(f"🚨 AWS connection error: {e}")
    st.stop()

# --- API Key Configuration ---
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)

    # Email configuration - Add better defaults and debugging
    EMAIL_ADDRESS = st.secrets.get("EMAIL_ADDRESS", "")
    EMAIL_PASSWORD = st.secrets.get("EMAIL_PASSWORD", "")
    CRISIS_ALERT_EMAIL = "kaemonng1017@gmail.com"

    # Show email config status for debugging (remove in production)
    if st.secrets.get("DEBUG_MODE", False):
        st.sidebar.info(f"Email configured: {bool(EMAIL_ADDRESS and EMAIL_PASSWORD)}")

except KeyError:
    st.error("🚨 Gemini API Key not found! Please add it to your Streamlit secrets.")
    st.stop()

# --- Model & Session Initialization ---
model = genai.GenerativeModel('gemini-1.5-flash-latest')

if "messages" not in st.session_state:
    st.session_state.messages = []
if "mood_data" not in st.session_state:
    st.session_state.mood_data = []
    try:
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(USER_ID)
        )
        for item in response['Items']:
            st.session_state.mood_data.append({
                'time': datetime.datetime.fromisoformat(item['timestamp']),
                'score': int(item['score']) if isinstance(item['score'], Decimal) else int(item['score']),
                'journal': item.get('journal', '')
            })
    except ClientError as e:
        st.error(f"Error loading data from DynamoDB: {e}")


# --- Enhanced Crisis Detection Functions ---
def detect_crisis_keywords(user_input):
    """Detect if user input contains crisis/suicide-related content - Enhanced version"""

    # Direct suicide/self-harm keywords
    direct_crisis_keywords = [
        'kill myself', 'suicide', 'suicidal', 'end my life', 'want to die', 'want die',
        'kill me', 'end it all', 'not worth living', 'better off dead',
        'hurt myself', 'harm myself', 'self harm', 'cut myself',
        'overdose', 'jump off', 'hang myself', 'shoot myself',
        'wanna die', 'want 2 die', 'gonna kill myself', 'going to kill myself',
        'i want to kill myself', 'want to end my life', 'planning to kill myself',
        'thinking of suicide', 'considering suicide', 'contemplating suicide',
        'take my own life', 'end my suffering', 'nothing to live for'
    ]

    # Indirect crisis indicators - these suggest severe hopelessness
    indirect_crisis_keywords = [
        'no reason to continue living', 'no reason to live', 'reason to continue living',
        'no point in living', 'no point to live', 'point in living',
        'life is meaningless', 'life has no meaning', 'no meaning in life',
        'nothing left to live for', 'nothing to live for', 'nothing left in life',
        'world would be better without me', 'better without me', 'nobody would care if i died',
        'nobody would miss me', 'no one would miss me', 'disappear forever',
        'give up on life', 'giving up on life', 'given up on life',
        'cant go on', "can't go on", 'cannot go on', 'cant take it anymore',
        "can't take it anymore", 'cannot take it anymore', 'had enough of life',
        'tired of living', 'tired of being alive', 'done with life',
        'want it to end', 'want everything to end', 'make it stop',
        'escape from everything', 'escape this life', 'permanent solution'
    ]

    # Phrases that combined with negative context indicate high risk
    contextual_risk_phrases = [
        'no reason for me to continue', 'no reason to continue',
        'nothing left for me', 'nothing left in my life',
        'life as a human being', 'failed at everything',
        'everything is meaningless', 'no meaning', 'meaningless',
        'nobody cares', 'no one cares', 'all alone',
        'complete failure', 'total failure', 'failure at life'
    ]

    user_input_lower = user_input.lower().strip()

    # Check for direct crisis keywords
    for keyword in direct_crisis_keywords:
        if keyword in user_input_lower:
            return True

    # Check for indirect crisis keywords
    for keyword in indirect_crisis_keywords:
        if keyword in user_input_lower:
            return True

    # Enhanced contextual analysis
    # Count risk indicators in the message
    risk_score = 0
    contextual_matches = []

    for phrase in contextual_risk_phrases:
        if phrase in user_input_lower:
            risk_score += 1
            contextual_matches.append(phrase)

    # Additional risk factors
    high_risk_combinations = [
        ('failure' in user_input_lower and 'meaningless' in user_input_lower),
        ('no friend' in user_input_lower and 'bullied' in user_input_lower),
        ('nothing left' in user_input_lower and ('continue' in user_input_lower or 'living' in user_input_lower)),
        ('no meaning' in user_input_lower and 'life' in user_input_lower),
        ('nobody' in user_input_lower and 'care' in user_input_lower),
        ('alone' in user_input_lower and ('meaningless' in user_input_lower or 'failure' in user_input_lower))
    ]

    for combination in high_risk_combinations:
        if combination:
            risk_score += 2

    # Specific patterns that indicate suicidal ideation without explicit mention
    suicidal_patterns = [
        'no reason.*continue.*living',
        'nothing left.*life',
        'no point.*living',
        'tired.*living',
        'done.*life',
        'give up.*life',
        'escape.*life',
        'end.*suffering',
        'make.*stop',
        'nothing.*live for'
    ]

    for pattern in suicidal_patterns:
        if re.search(pattern, user_input_lower):
            risk_score += 3

    # If risk score is high enough, consider it a crisis
    if risk_score >= 3:
        return True

    # Special case: Check for the exact type of message you showed
    # "no reason for me to continue living" type messages
    if ('continue' in user_input_lower and 'living' in user_input_lower and
            ('no reason' in user_input_lower or 'dont feel' in user_input_lower or "don't feel" in user_input_lower)):
        return True

    return False


def analyze_crisis_severity(user_input):
    """Analyze the severity level of crisis content"""
    user_input_lower = user_input.lower().strip()

    # Immediate danger indicators
    immediate_danger = [
        'tonight', 'today', 'right now', 'planning to', 'going to',
        'have pills', 'have rope', 'have gun', 'made plan',
        'decided to', 'ready to', 'about to'
    ]

    # High risk indicators
    high_risk = [
        'no reason to continue living', 'nothing left to live for',
        'world better without me', 'nobody would miss me',
        'tired of living', 'done with life', 'give up on life'
    ]

    # Moderate risk indicators
    moderate_risk = [
        'meaningless', 'no meaning', 'failure at everything',
        'nobody cares', 'all alone', 'nothing left'
    ]

    severity = "LOW"

    for phrase in immediate_danger:
        if phrase in user_input_lower:
            return "IMMEDIATE"

    for phrase in high_risk:
        if phrase in user_input_lower:
            severity = "HIGH"

    for phrase in moderate_risk:
        if phrase in user_input_lower:
            if severity != "HIGH":
                severity = "MODERATE"

    return severity


def get_severity_recommendations(severity):
    """Get recommended actions based on crisis severity"""
    if severity == "IMMEDIATE":
        return """
RECOMMENDED ACTIONS:
1. IMMEDIATE phone contact with user if possible
2. Consider emergency services notification
3. Escalate to crisis counselor immediately
4. Follow up within 1 hour
        """
    elif severity == "HIGH":
        return """
RECOMMENDED ACTIONS:
1. Priority response within 30 minutes
2. Direct counselor intervention recommended
3. Safety planning session needed
4. Follow up within 2-4 hours
        """
    else:
        return """
RECOMMENDED ACTIONS:
1. Response within 1-2 hours
2. Supportive counseling session
3. Monitor for escalation
4. Follow up within 24 hours
        """


def send_enhanced_crisis_email(user_message, timestamp, severity="HIGH"):
    """Send enhanced emergency notification email with severity level"""
    try:
        # Check if email credentials are configured
        if not EMAIL_ADDRESS or not EMAIL_PASSWORD or EMAIL_ADDRESS == "your_email@gmail.com":
            st.warning("📧 Email credentials not configured. Crisis alert logged locally only.")
            st.info(f"🚨 CRISIS DETECTED ({severity}): {timestamp} - User message: {user_message}")
            return False

        # Create the email content with severity
        subject = f"🚨 {severity} CRISIS ALERT - Counselling App"

        body = f"""
EMERGENCY CRISIS ALERT - {severity} SEVERITY

Timestamp: {timestamp}
User ID: {USER_ID}
Severity Level: {severity}

Message from user:
"{user_message}"

CRISIS ANALYSIS:
- Crisis keywords detected: YES
- Severity assessment: {severity}
- Immediate intervention may be required

This is an automated alert from the Accessible Counselling Assistant.
A user has expressed concerning content that may indicate suicidal ideation or self-harm.

{get_severity_recommendations(severity)}

Please take immediate action as per your crisis intervention protocols.

---
Enhanced Crisis Detection System
Accessible Counselling Assistant
        """

        # Create email message
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = CRISIS_ALERT_EMAIL
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'plain'))

        # Send the email using Gmail SMTP with proper authentication
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)

        st.success(f"✅ {severity} crisis email sent successfully to {CRISIS_ALERT_EMAIL}")
        return True

    except Exception as e:
        st.error(f"📧 Email sending failed: {str(e)}")
        st.info(f"🚨 CRISIS LOGGED LOCALLY ({severity}): {timestamp} - {user_message}")
        return False


def enhanced_crisis_response_footer(severity="HIGH"):
    """Enhanced emergency contact information based on severity"""

    base_response = """

🚨 IMMEDIATE SUPPORT NEEDED 🚨

Your message shows you're in significant emotional distress. You are not alone, and help is available right now.

"""

    if severity == "IMMEDIATE":
        base_response += """
⚠️ If you're in immediate danger, please:
• Call 999 (Malaysia Emergency) NOW
• Go to your nearest hospital emergency room
• Call someone to stay with you

"""

    base_response += """
24/7 Crisis Hotlines (Malaysia):
• Befrienders KL: 03-7627 2929
• Talian Kasih: 15999
• Mental Health Support: 03-2935 9935
• Suicide Prevention: 1800-18-2327

International:
• Crisis Text Line: Text HOME to 741741
• Samaritans: 116 123 (UK/Ireland)

Online Support:
• Befrienders: www.befrienders.org.my
• Crisis Chat: Available 24/7

Remember:
✓ Your pain is temporary, but suicide is permanent
✓ You matter and your life has value
✓ Many people who felt like you do have found hope again
✓ Professional help can make a real difference

Please reach out to one of these resources right now. You deserve support and care.

"""
    return base_response


def is_emotional_content(user_input):
    """Check if user input contains emotional content worth tracking"""
    # Always track crisis content
    if detect_crisis_keywords(user_input):
        return True

    # Filter out very short non-emotional queries
    user_input_lower = user_input.lower().strip()

    # Skip very short generic questions/greetings
    short_non_emotional = [
        'hi', 'hello', 'hey', 'ok', 'okay', 'yes', 'no', 'thanks', 'thank you',
        'what', 'how', 'why', 'when', 'where', 'who', 'can you', 'could you',
        'tell me', 'explain', 'help me', 'how can i', 'what can i', 'how do i',
        'what should i', 'can i', 'is it', 'do you', 'are you', 'will you'
    ]

    # If it's a very short message and matches non-emotional patterns, skip it
    words = user_input_lower.split()
    if len(words) <= 5:
        if any(user_input_lower.startswith(phrase) for phrase in short_non_emotional):
            return False
        if user_input_lower in short_non_emotional:
            return False

    # Words that indicate emotional content
    emotion_indicators = [
        # Direct feelings
        'feel', 'feeling', 'felt', 'emotions', 'emotional',
        # Positive emotions
        'happy', 'joyful', 'excited', 'love', 'grateful', 'hopeful', 'proud',
        'content', 'peaceful', 'confident', 'elated', 'thrilled', 'amazing',
        # Negative emotions
        'sad', 'angry', 'hate', 'fear', 'anxious', 'worried', 'stressed',
        'depressed', 'frustrated', 'disappointed', 'ashamed', 'guilty',
        'lonely', 'overwhelmed', 'nervous', 'upset', 'hurt', 'broken',
        'devastated', 'exhausted', 'tired', 'drained',
        # Mood expressions
        'mood', 'today i', 'right now i', 'currently i', 'i am', "i'm",
        # Personal experiences that usually involve emotions
        'my day', 'happened to me', 'going through', 'dealing with',
        'struggling with', 'hard time', 'difficult', 'tough day'
    ]

    # Check for emotional indicators
    for indicator in emotion_indicators:
        if indicator in user_input_lower:
            return True

    # Check if it's a personal statement that likely involves emotions
    personal_patterns = [
        'i feel', 'i am', "i'm ", 'i have been', 'i was', 'i think i',
        'my life', 'my family', 'my work', 'my relationship', 'my mental',
        'today has been', 'lately i', 'recently i'
    ]

    for pattern in personal_patterns:
        if pattern in user_input_lower:
            return True

    return False


def get_mood_emoji_and_class(score):
    """Convert mood score to emoji and CSS class"""
    if score >= 8:
        return "😄", "mood-very-positive"
    elif score >= 6:
        return "😊", "mood-positive"
    elif score >= 4:
        return "🙂", "mood-neutral"
    elif score >= 2:
        return "😐", "mood-neutral"
    elif score >= -2:
        return "😕", "mood-negative"
    elif score >= -6:
        return "😢", "mood-negative"
    else:
        return "😭", "mood-very-negative"


def analyze_mood_score(user_input):
    """Analyze user input and return a mood score from -10 to +10"""
    mood_prompt = (
        "You are an expert emotion analyst. Analyze the emotional sentiment and intensity of the following text. "
        "Rate the overall mood on a scale from -10 to +10 where:\n\n"
        "NEGATIVE EMOTIONS:\n"
        "-10: Extremely negative (suicidal thoughts, severe depression, complete despair)\n"
        "-9: Severe distress (panic attacks, overwhelming anxiety, deep trauma)\n"
        "-8: Very negative (major depression, intense grief, severe hopelessness)\n"
        "-7: High distress (strong anxiety, significant sadness, major worry)\n"
        "-6: Moderately negative (depression, fear, distress, strong worry)\n"
        "-5: Negative (sadness, frustration, anxiety, worry, disappointment)\n"
        "-4: Mild negative (concern, mild sadness, slight worry, irritation)\n"
        "-3: Slightly negative (minor worry, mild disappointment, slight stress)\n"
        "-2: Barely negative (small concerns, tiny worries)\n"
        "-1: Very slightly negative (minor unease)\n\n"
        "NEUTRAL:\n"
        "0: Completely neutral (no emotional content, factual statements)\n\n"
        "POSITIVE EMOTIONS:\n"
        "+1: Very slightly positive (tiny bit happy, mild relief)\n"
        "+2: Barely positive (small satisfaction, slight comfort)\n"
        "+3: Slightly positive (mild happiness, slight optimism, small joy)\n"
        "+4: Mild positive (content, pleased, hopeful, relieved)\n"
        "+5: Positive (happy, optimistic, satisfied, grateful)\n"
        "+6: Moderately positive (joyful, excited, very happy)\n"
        "+7: High positive (elated, thrilled, very excited)\n"
        "+8: Very positive (euphoric, overjoyed, ecstatic)\n"
        "+9: Extreme positive (manic happiness, overwhelming joy)\n"
        "+10: Maximum positive (peak euphoria, ultimate bliss)\n\n"
        "IMPORTANT EXAMPLES:\n"
        "- 'I'm worried about my exam' = -4 or -5 (worry is negative)\n"
        "- 'I'm anxious about tomorrow' = -5 or -6 (anxiety is negative)\n"
        "- 'I'm stressed about work' = -4 or -5 (stress is negative)\n"
        "- 'I'm exhausted now' = -5 or -6 (exhaustion is negative)\n"
        "- 'I'm tired' = -3 or -4 (tiredness is negative)\n"
        "- 'I'm excited about the party' = +5 or +6 (excitement is positive)\n"
        "- 'I'm very excited now' = +6 or +7 (very excited is very positive)\n"
        "- 'I feel excited' = +5 or +6 (excited is positive)\n"
        "- 'I feel okay today' = 0 or +1 (neutral to slightly positive)\n"
        "- 'I'm devastated' = -8 or -9 (very negative)\n\n"
        "Be precise and consider the emotional weight of words like worried, anxious, stressed, sad, happy, excited, etc.\n"
        "Respond with ONLY a single number from -10 to +10. No explanation, just the number.\n\n"
        f'Text to analyze: "{user_input}"'
    )

    try:
        response = model.generate_content(mood_prompt)
        score_text = response.text.strip()
        # Extract number from response
        numbers = re.findall(r'-?\d+', score_text)
        if numbers:
            score = int(numbers[0])
            # Clamp score between -10 and +10
            return max(-10, min(10, score))
        else:
            # Fallback keyword analysis
            return analyze_mood_keywords(user_input)
    except Exception as e:
        print(f"Error analyzing mood: {e}")
        return analyze_mood_keywords(user_input)


def analyze_mood_keywords(user_input):
    """Fallback keyword-based mood analysis"""
    text_lower = user_input.lower()

    # Crisis keywords
    if any(word in text_lower for word in
           ['kill myself', 'suicide', 'want to die', 'end my life', 'better off dead']):
        return -10

    # Very negative
    if any(word in text_lower for word in
           ['devastated', 'hopeless', 'worthless', 'hate myself', 'can\'t go on']):
        return -8

    # Negative emotions
    if any(word in text_lower for word in
           ['exhausted', 'drained', 'burnt out', 'overwhelmed', 'miserable']):
        return -6
    elif any(word in text_lower for word in
             ['tired', 'fatigued', 'weary', 'worn out', 'sleepy']):
        return -4
    elif any(word in text_lower for word in
             ['worried', 'anxious', 'stressed', 'concerned', 'nervous']):
        return -4
    elif any(word in text_lower for word in
             ['sad', 'upset', 'disappointed', 'frustrated', 'angry']):
        return -5

    # Positive emotions
    elif any(word in text_lower for word in
             ['excited', 'thrilled', 'elated', 'overjoyed', 'ecstatic']):
        return 6
    elif any(word in text_lower for word in
             ['happy', 'joyful', 'great', 'wonderful', 'fantastic']):
        return 5
    elif any(word in text_lower for word in
             ['good', 'pleased', 'content', 'satisfied', 'grateful']):
        return 4
    elif any(word in text_lower for word in
             ['okay', 'fine', 'alright', 'normal', 'decent']):
        return 1
    else:
        return 0


# --- Data Persistence Function ---
def save_mood_data(score, journal_text):
    timestamp_str = datetime.datetime.now().isoformat()
    try:
        table.put_item(
            Item={
                'user_id': USER_ID,
                'timestamp': timestamp_str,
                'score': Decimal(str(score)),
                'journal': journal_text
            }
        )
        return {"time": datetime.datetime.fromisoformat(timestamp_str), "score": int(score), "journal": journal_text}
    except ClientError as e:
        st.error(f"Error saving data to DynamoDB: {e}")
        return None


# --- Main App Title and Description ---
st.title("Accessible Counselling Assistant 💬")
st.markdown("A safe space to share your feelings and receive compassionate support.")

# --- Sidebar: Your Mood Tracker & Insights ---
with st.sidebar:
    st.header("Your Mood Tracker")
    if st.session_state.mood_data:
        timestamps = [item['time'] for item in st.session_state.mood_data]
        mood_scores = [item['score'] for item in st.session_state.mood_data]
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot(timestamps, mood_scores, marker='o', linestyle='-', color='#4CAF50', linewidth=2, markersize=6)
        ax.set_title("Your Mood Over Time", fontsize=16, fontweight='bold')
        ax.set_ylabel("Mood Score", fontsize=12)
        ax.set_xlabel("Time of Day", fontsize=12)
        ax.set_ylim(-11, 11)
        ax.axhline(0, color='white', linewidth=0.8, linestyle='--')
        ax.fill_between(timestamps, mood_scores, 0, color='#4CAF50', alpha=0.3)
        ax.set_xticks(timestamps)
        ax.set_xticklabels([t.strftime("%H:%M") for t in timestamps], rotation=45, ha="right")
        ax.grid(axis='y', linestyle='--', alpha=0.7)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        # Add mood level indicators
        ax.axhspan(6, 10, alpha=0.1, color='green', label='Very Positive')
        ax.axhspan(2, 6, alpha=0.1, color='lightgreen', label='Positive')
        ax.axhspan(-2, 2, alpha=0.1, color='gray', label='Neutral')
        ax.axhspan(-6, -2, alpha=0.1, color='orange', label='Negative')
        ax.axhspan(-10, -6, alpha=0.1, color='red', label='Very Negative')

        plt.tight_layout()
        st.pyplot(fig)

        # Show current mood status
        if mood_scores:
            latest_score = mood_scores[-1]
            emoji, _ = get_mood_emoji_and_class(latest_score)
            st.markdown(f"**Latest Mood:** {emoji} {latest_score}/10")
    else:
        st.info("Start chatting to track your mood!")

    st.markdown("---")
    st.header("Quick Help Tools")

    # Crisis Hotlines (always visible)
    with st.expander("🚨 Crisis Hotlines", expanded=False):
        st.write("**Befrienders KL:** 03-7627 2929")
        st.write("**Talian Kasih:** 15999")
        st.write("**Emergency:** 999")
        st.write("**Mental Health:** 03-2935 9935")

    # Breathing Exercise
    if st.button("🫁 Start Breathing Exercise"):
        breathing_prompt = (
            "Generate a personalized, calming breathing exercise guide. "
            "Make it warm, encouraging, and unique each time. Include specific instructions "
            "and gentle, supportive language. Keep it under 100 words and make it feel like "
            "a caring counselor is guiding them through it."
        )
        try:
            with st.spinner("Creating your breathing guide..."):
                response = model.generate_content(breathing_prompt)
                breathing_content = response.text.strip()

                # Clean the response
                breathing_content = breathing_content.replace('</div>', '').replace('<div>', '')
                breathing_content = re.sub(r'<[^>]*>', '', breathing_content)

                # Add as AI message
                st.session_state.messages.append(
                    {"role": "assistant", "content": f"🫁 **Breathing Exercise**\n\n{breathing_content}"})
                st.rerun()
        except Exception as e:
            fallback_breathing = "🫁 **Breathing Exercise**\n\nTake a moment with me. Breathe in slowly for 4 counts, hold gently for 4, then exhale for 6. Let your shoulders drop. You're doing great."
            st.session_state.messages.append({"role": "assistant", "content": fallback_breathing})
            st.rerun()

    # Wellness Games
    if st.button("🎯 Wellness Games"):
        wellness_prompt = (
            "Suggest and guide me through one creative, evidence-based therapeutic activity or mindfulness game "
            "that can help with anxiety, stress, or difficult emotions. Choose from techniques like grounding exercises, "
            "mindfulness activities, breathing games, sensory awareness, gratitude practices, visualization, "
            "progressive muscle relaxation, cognitive reframing exercises, or any other therapeutic technique. "
            "Make it interactive, unique, and provide step-by-step guidance. Keep it under 120 words and "
            "use warm, encouraging language. Create something different each time."
        )

        try:
            with st.spinner("Choosing a wellness activity for you..."):
                response = model.generate_content(wellness_prompt)
                activity_content = response.text.strip()

                # Clean the response
                activity_content = activity_content.replace('</div>', '').replace('<div>', '')
                activity_content = re.sub(r'<[^>]*>', '', activity_content)

                # Add as AI message
                st.session_state.messages.append(
                    {"role": "assistant", "content": f"🎯 **Wellness Activity**\n\n{activity_content}"})
                st.rerun()
        except Exception as e:
            fallback_activities = [
                "🎯 **Body Scan Check-in**\n\nClose your eyes and mentally scan from your head to your toes. Notice any tension without trying to change it. Just acknowledge: 'I notice my shoulders are tight' or 'My jaw feels relaxed.' This awareness is the first step to releasing stress.",
                "🎯 **Temperature Awareness**\n\nFind something cool to touch, then something warm. Notice the contrast. How does each temperature make you feel emotionally? Sometimes physical sensations can shift our emotional state in surprising ways.",
                "🎯 **Name That Emotion**\n\nInstead of saying 'I feel bad,' try to name the specific emotion: frustrated, disappointed, overwhelmed, worried? Naming emotions with precision can actually reduce their intensity."
            ]
            import random

            chosen_fallback = random.choice(fallback_activities)
            st.session_state.messages.append({"role": "assistant", "content": chosen_fallback})
            st.rerun()

    # Positive Affirmation
    if st.button("✨ Get Affirmation"):
        affirmation_prompt = (
            "Generate a personalized, meaningful positive affirmation. "
            "Make it warm, empowering, and specific to someone who might be struggling. "
            "Avoid generic phrases. Make it feel personal and encouraging. "
            "Include a brief explanation of why this affirmation matters. "
            "Keep it under 80 words total."
        )
        try:
            with st.spinner("Creating your personal affirmation..."):
                response = model.generate_content(affirmation_prompt)
                affirmation_content = response.text.strip()

                # Clean the response
                affirmation_content = affirmation_content.replace('</div>', '').replace('<div>', '')
                affirmation_content = re.sub(r'<[^>]*>', '', affirmation_content)

                # Add as AI message
                st.session_state.messages.append(
                    {"role": "assistant", "content": f"✨ **Your Personal Affirmation**\n\n{affirmation_content}"})
                st.rerun()
        except Exception:
            import random

            fallback_affirmations = [
                "You are exactly where you need to be in your journey. Every step, even the difficult ones, is teaching you something valuable.",
                "Your feelings are valid and you have the strength to work through them. You've overcome challenges before.",
                "You matter more than you know. Your presence in this world makes a difference, even in small ways.",
                "It's okay to not be okay right now. Healing isn't linear, and you're being brave by seeking support."
            ]
            chosen_affirmation = random.choice(fallback_affirmations)
            st.session_state.messages.append(
                {"role": "assistant", "content": f"✨ **Your Personal Affirmation**\n\n{chosen_affirmation}"})
            st.rerun()

    st.markdown("---")
    st.header("Get Insights")
    if st.button("Analyze My Moods"):
        if st.session_state.mood_data:
            mood_log = []
            for item in st.session_state.mood_data:
                time_str = item['time'].strftime("%Y-%m-%d %H:%M")
                score = item['score']
                journal_entry = item.get('journal', 'No journal entry.')
                mood_log.append(f"On {time_str}, my mood was {score}/10. Journal entry: {journal_entry}")

            insights_prompt = (
                    "You are an empathetic and insightful AI assistant. Analyze the following mood log to identify any patterns or trends. "
                    "The mood scores range from -10 (extremely negative) to +10 (extremely positive). "
                    "Provide a short, gentle summary and a piece of encouraging advice. Do not provide medical advice. "
                    "Mood Log:\n" + "\n".join(mood_log)
            )
            with st.spinner("Analyzing your mood data..."):
                try:
                    insights_response = model.generate_content(insights_prompt)
                    st.success("Analysis complete!")
                    st.info(insights_response.text)
                except Exception as e:
                    st.error(f"Error during insights analysis: {e}")
        else:
            st.info("No mood data to analyze yet. Start chatting to begin tracking!")

# --- Display Chat History with Avatars ---
for i, message in enumerate(st.session_state.messages):
    if message["role"] == "user":
        escaped_content = message["content"].replace('<', '&lt;').replace('>', '&gt;')
        st.markdown(
            f'''
            <div class="chat-container user-container">
                <div class="avatar user-avatar">👤</div>
                <div class="chat-bubble user-bubble">
                    {escaped_content}
                </div>
            </div>
            ''',
            unsafe_allow_html=True
        )
    else:
        escaped_content = message["content"].replace('<', '&lt;').replace('>', '&gt;')
        st.markdown(
            f'''
            <div class="chat-container assistant-container">
                <div class="avatar assistant-avatar">🤖</div>
                <div class="chat-bubble assistant-bubble">
                    {escaped_content}
                </div>
            </div>
            ''',
            unsafe_allow_html=True
        )

# --- Enhanced User Input & Interaction ---
journal_checkbox = st.checkbox("Save this as a journal entry")
user_input = st.chat_input("How are you feeling today?")

if user_input:
    # Enhanced crisis detection
    is_crisis = detect_crisis_keywords(user_input)
    crisis_severity = "LOW"

    # If crisis detected, analyze severity and send email immediately
    if is_crisis:
        crisis_severity = analyze_crisis_severity(user_input)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        email_sent = send_enhanced_crisis_email(user_input, timestamp, crisis_severity)

        # Show enhanced crisis alert with severity
        alert_color = {
            "IMMEDIATE": "#ff0000",
            "HIGH": "#ff4444",
            "MODERATE": "#ff8800",
            "LOW": "#ffaa00"
        }.get(crisis_severity, "#ff4444")

        st.markdown(
            f'''
            <div class="crisis-alert" style="background: linear-gradient(135deg, {alert_color} 0%, #cc0000 100%);">
                <h3>🚨 {crisis_severity} SEVERITY CRISIS DETECTED</h3>
                <p><strong>We've detected that you may be in serious emotional distress. Your safety is our top priority.</strong></p>
                <p>Crisis severity: <strong>{crisis_severity}</strong></p>
                <p>Emergency notification sent: {"✅ Yes" if email_sent else "❌ Failed"}</p>
                <p><strong>Please reach out to emergency support immediately:</strong></p>
                <p>🇲🇾 <strong>Befrienders KL: 03-7627 2929 (24/7)</strong></p>
                <p>🆘 <strong>Emergency: 999</strong></p>
            </div>
            ''',
            unsafe_allow_html=True
        )

    # Only analyze and save mood if it's emotional content
    if is_emotional_content(user_input):
        mood_score = analyze_mood_score(user_input)

        # For crisis situations, ensure mood score reflects severity
        if is_crisis:
            if crisis_severity in ["IMMEDIATE", "HIGH"]:
                mood_score = min(mood_score, -8)  # Ensure very negative score
            elif crisis_severity == "MODERATE":
                mood_score = min(mood_score, -6)

        # Save mood data
        journal_text = user_input if journal_checkbox else ""
        new_mood_data = save_mood_data(mood_score, journal_text)
        if new_mood_data:
            st.session_state.mood_data.append(new_mood_data)

    # Add user message to chat
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.spinner("Thinking with empathy..."):
        try:
            # Enhanced prompt for crisis situations
            if is_crisis:
                crisis_prompt = f"""
You are a compassionate crisis counseling assistant. The user has expressed content suggesting suicidal ideation or severe emotional distress (severity: {crisis_severity}).

CRITICAL GUIDELINES:
1. Acknowledge their pain and validate their feelings
2. Express genuine concern for their safety
3. Gently guide them toward professional help
4. DO NOT minimize their feelings or offer quick fixes
5. Emphasize that help is available and effective
6. Be warm but direct about the seriousness
7. Keep response under 200 words

The user said: "{user_input}"

Respond with empathy while emphasizing the importance of professional support.
"""
                response = model.generate_content(crisis_prompt)
            else:
                # Create regular conversation context
                prompt_parts = [
                    "You are a compassionate, gentle, and empathetic counselling assistant. Your role is to listen, validate the user's feelings, and offer supportive, non-judgmental feedback. Do not give medical advice. Keep your response concise (under 150 words) and warm.",
                    "Here is our conversation history:",
                ]

                for message in st.session_state.messages:
                    if message["role"] == "user":
                        prompt_parts.append(f"User: {message['content']}")
                    else:
                        prompt_parts.append(f"Assistant: {message['content']}")

                prompt_parts.append(f"User: {user_input}")
                prompt_parts.append(f"Assistant:")

                response = model.generate_content(" ".join(prompt_parts))

            assistant_response = response.text

            # Clean HTML and formatting issues
            assistant_response = assistant_response.replace('</div>', '')
            assistant_response = assistant_response.replace('<div>', '')
            assistant_response = assistant_response.replace('</DIV>', '')
            assistant_response = assistant_response.replace('<DIV>', '')

            # Aggressive HTML tag removal
            html_patterns_to_remove = [
                '</div>', '<div>', '</DIV>', '<DIV>',
                '</span>', '<span>', '</SPAN>', '<SPAN>',
                '</p>', '<p>', '</P>', '<P>',
                '<br>', '<BR>', '<br/>', '<BR/>',
                '</strong>', '<strong>', '</STRONG>', '<STRONG>',
                '</em>', '<em>', '</EM>', '<EM>'
            ]

            for pattern in html_patterns_to_remove:
                assistant_response = assistant_response.replace(pattern, '')

            # Remove all HTML tags with regex
            assistant_response = re.sub(r'</?[^>]+/?>', '', assistant_response)
            assistant_response = re.sub(r'<[^>]*>', '', assistant_response)
            assistant_response = re.sub(r'</?\s*div[^>]*>', '', assistant_response, flags=re.IGNORECASE)
            assistant_response = re.sub(r'</?\s*span[^>]*>', '', assistant_response, flags=re.IGNORECASE)
            assistant_response = re.sub(r'<[/]?[\w\s="\']*>', '', assistant_response)

            # Clean up extra whitespace
            assistant_response = re.sub(r'\n\s*\n\s*\n', '\n\n', assistant_response)
            assistant_response = assistant_response.strip()

            # If crisis was detected, append appropriate emergency resources
            if is_crisis:
                assistant_response += enhanced_crisis_response_footer(crisis_severity)

            # Final cleanup
            assistant_response = re.sub(r'<[^>]*>', '', assistant_response)
            assistant_response = assistant_response.strip()

            st.session_state.messages.append({"role": "assistant", "content": assistant_response})
            st.rerun()

        except Exception as e:
            # Fallback crisis response if API fails
            if is_crisis:
                fallback_response = f"""I can hear how much pain you're in right now, and I'm genuinely concerned about you. What you're feeling is real and valid, but please know that these overwhelming feelings can change with proper support.

You mentioned feeling like there's no reason to continue living - that tells me you're in a mental health crisis that needs immediate professional attention. This isn't something you have to face alone.

{enhanced_crisis_response_footer(crisis_severity)}"""
                st.session_state.messages.append({"role": "assistant", "content": fallback_response})
            else:
                st.error(f"An error occurred: {e}")
            st.rerun()