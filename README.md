# my-telegram-bot
Telegram bot for learning Python

Context-aware Telegram assistant based on OpenRouter models' AI


## Features
- 🧠 AI-powered responses using OpenRouter's model
- ⚡️ Context-aware conversations (last 5 messages)
- 🔒 Rate limiting (5 requests/minute per user)
- 💬 Custom system prompts for different chat groups
- ✨ Automatic typing indicators
- 🧹 Background context cleanup


## Requirements
- Python 3.9+
- Telegram bot token
- [OpenRouter API key](https://openrouter.ai/keys)


## Installation
1. Clone repository: ```bash
git clone https://github.com/dionisty/my-telegram-bot.git
cd my-telegram-bot

2. Install dependencies:
pip install -r requirements.txt

3. Create .env file:
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OPENROUTER_API_KEY=your_openrouter_api_key


## Configuration
Customize chat settings in bot.py:
chat_settings = {
    ID_chat: {
        "system_prompt": "Your custom prompt...",
        "context_length": 5
    }
}


## Usage
Run the bot: python bot.py

Interact in Telegram:
Mention @your_bot_username
Reply to bot's messages

Commands:
/start - Get welcome message
/help - Show instructions


## Technical Stack

python-telegram-bot - Telegram API
openai - OpenRouter API client
python-dotenv - Environment management
Multi-threading for background tasks


Key elements included:
1. Clear feature list with emojis
2. Simple installation steps
3. Environment setup instructions
4. Configuration guidance
5. Usage examples
6. Technology stack

The README focuses on essential setup/usage while highlighting the bot's unique features like context management and specialized prompts for trading communities. Adjust repository links and license as needed for your project.
