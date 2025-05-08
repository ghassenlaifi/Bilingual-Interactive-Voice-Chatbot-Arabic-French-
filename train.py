from chatterbot.trainers import ListTrainer
import json
from chatterbot import ChatBot
import nltk
nltk.download('punkt_tab')
# Initialize the chatbot
chatbot = ChatBot(
    'Orrif',
    storage_adapter='chatterbot.storage.SQLStorageAdapter',
    database_uri='sqlite:///database.sqlite3',
    logic_adapters=[
        {
            'import_path': 'chatterbot.logic.BestMatch',
            'default_response': "أنا آسف، ليس لدي إجابة على ذلك.",
            'maximum_similarity_threshold': 0.80
        }
    ]
)

# Function to train the chatbot
def train_bot(file_path, trainer):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            conversations = json.load(file)
        for conversation in conversations:
            if isinstance(conversation, list) and len(conversation) > 1:
                trainer.train(conversation)
    except FileNotFoundError:
        print(f"Dataset file '{file_path}' not found.")

# Train the chatbot with datasets
print("Training with French dataset...")
train_bot('french.json', ListTrainer(chatbot))
print("French dataset training complete.")

print("Training with Arabic dataset...")
train_bot('arabic.json', ListTrainer(chatbot))
print("Arabic dataset training complete.")
