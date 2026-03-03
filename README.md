# 🧠 AI Counselling Assistant

An AI-powered mental health support prototype built during a hackathon, designed to provide empathetic, stigma-free counselling and personalized coping strategies.

## ✨ Features

- 💬 Empathetic AI responses using Google Gemini
- 📊 Mood tracking to monitor emotional wellbeing over time
- 📔 Secure personal journaling
- ☁️ Cloud-backed storage with AWS DynamoDB
- 🤝 Stigma-free, accessible mental health support

## 🛠️ Tech Stack

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)
![AWS](https://img.shields.io/badge/AWS_DynamoDB-232F3E?style=flat-square&logo=amazonaws&logoColor=white)
![Google Gemini](https://img.shields.io/badge/Google_Gemini-4285F4?style=flat-square&logo=google&logoColor=white)

## 🚀 Getting Started

### Prerequisites
- Python 3.x
- AWS credentials (DynamoDB access)
- Google Gemini API key

### Installation

```bash
# Clone the repository
git clone https://github.com/Kaemon/AWS-Hackathon.git
cd AWS-Hackathon

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Create a `.streamlit/secrets.toml` file with your credentials:

```toml
AWS_ACCESS_KEY_ID = "your_aws_access_key"
AWS_SECRET_ACCESS_KEY = "your_aws_secret_key"
GEMINI_API_KEY = "your_gemini_api_key"
```

### Run

```bash
streamlit run app.py
```

## 👥 Team

Built by a team of 4 during a hackathon under time pressure.

## 📚 About

Developed as a hackathon prototype to explore how AI can make mental health support more accessible and stigma-free.
