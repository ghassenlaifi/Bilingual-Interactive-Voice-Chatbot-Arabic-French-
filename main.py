from flask import Flask, jsonify
from flask_socketio import SocketIO, emit
import speech_recognition as sr
from pyt2s.services import stream_elements
from chatterbot import ChatBot
from pydub import AudioSegment
from pydub.playback import play
import io
import time
import logging
import sounddevice as sd
import numpy as np
from fuzzywuzzy import fuzz

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
default_response = "أنا آسف، ليس لدي إجابة على ذلك." 

# Initialize the chatbot
chatbot = ChatBot(
    'Orrif',
    storage_adapter='chatterbot.storage.SQLStorageAdapter',
    database_uri='sqlite:///database.sqlite3',
    logic_adapters=[
        {
            'import_path': 'chatterbot.logic.BestMatch',
            'default_response': default_response,
            'maximum_similarity_threshold': 0.80
        }
    ]
)

# Initialize the recognizer
recognizer = sr.Recognizer()

# Time constants
INACTIVITY_LIMIT = 60  # seconds

# Status variable
status = "idle"

# Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret'
app.config['SESSION_TYPE'] = 'filesystem'
socketio = SocketIO(app, cors_allowed_origins='*')


def set_status(new_status):
    global status
    status = new_status
    try:
        logger.info(f"Status changed to: {status}")
        socketio.emit('status_update', {'status': status})
    except Exception as e:
        logger.error(f"Failed to emit status update: {e}")

@app.route('/', methods=['GET'])
def get_status():
    logger.info("Received HTTP request for status")
    return jsonify({"status": status})

# WebSocket handling
@socketio.on('connect')
def handle_connect():
    logger.info("Client connected via WebSocket")
    emit('status_update', {'status': status})

@socketio.on('disconnect')
def handle_disconnect():
    logger.info("Client disconnected from WebSocket")

def speak(text, language):
    try:
        set_status("speaking")
        voice = stream_elements.Voice.ar_XA_Wavenet_B.value if language == 'ar' else stream_elements.Voice.Mathieu.value
        data = stream_elements.requestTTS(text, voice)
        audio_segment = AudioSegment.from_file(io.BytesIO(data), format="mp3")
        play(audio_segment)
    except Exception as e:
        logger.error(f"Error in text-to-speech: {e}")

def get_response(question):
    set_status("generating")
    try:
        response = chatbot.get_response(question)
        if response.text == chatbot.logic_adapters[0].default_response:
            return default_response
        return str(response)
    except Exception as e:
        logger.error(f"Error while getting chatbot response: {e}")
        return "Désolé, une erreur est survenue."

def listen_for_audio():
    try:
        fs = 16000  # Sample rate
        duration = 5  # seconds
        logger.info("Listening for audio...")
        set_status("listening")

        # Record audio for the set duration
        audio = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16')
        sd.wait()  # Wait until recording is finished

        # Convert the numpy array to bytes for compatibility with speech_recognition
        audio_bytes = np.frombuffer(audio, np.int16).tobytes()

        # Create an AudioData object from bytes for recognition
        audio_data = sr.AudioData(audio_bytes, fs, 2)
        return audio_data

    except Exception as e:
        logger.error(f"Error capturing audio: {e}")
        return None

def is_trigger_word_in_text(recognized_text):
    # List of possible trigger words in Arabic with slight variations
    trigger_words = ["عُرِيف", "عسلامة", "عُورِيف", "عَسْلَامة ريف", "عَسْلَامة الريف", "عُرْيِف", "عسلامة عُرِيفْ"]
    for word in trigger_words:
        logger.info(f"Comparing with word: {word}")  # Debugging step
        if fuzz.partial_ratio(word, recognized_text) > 60:  # Lower threshold to 60 for better flexibility
            return True
    return False

def listen_for_trigger():
    set_status("idle")
    logger.info("Listening for trigger word عُرِيف ...")
    while True:
        audio = listen_for_audio()
        if audio is None:
            continue
        try:
            recognized_text = recognizer.recognize_google(audio, language="ar-AR").strip()
            logger.info(f"Recognized: {recognized_text}")
            if is_trigger_word_in_text(recognized_text):
                return True
        except sr.UnknownValueError:
            logger.warning("Trigger word not understood.")
        except sr.RequestError as e:
            logger.error(f"Speech recognition service error: {e}")

def ask_language_preference():
    speak("هل تفضل التواصل باللغة العربية أو الفرنسية؟", language='ar')
    logger.info("Listening for user's language choice...")
    set_status("listening")
    while True:
        audio = listen_for_audio()
        if audio is None:
            continue
        try:
            recognized_text = recognizer.recognize_google(audio, language="ar-AR").strip().lower()
            logger.info(f"Language choice recognized: {recognized_text}")

            arabic_phrases = ["عربية", "العربية", "العربيه", "عربيه"]
            french_phrases = ["فرنسية", "الفرنسية", "الفرنسيه", "فرنسيه"]

            if any(phrase in recognized_text for phrase in arabic_phrases):
                speak("تم اختيار اللغة العربية.", language='ar')
                return 'ar'
            elif any(phrase in recognized_text for phrase in french_phrases):
                speak("تم اختيار اللغة الفرنسية.", language='ar')
                return 'fr'
            else:
                logger.info(f"Unrecognized language choice: {recognized_text}")
                speak("عذرًا، لم أفهم اللغة المختارة. يرجى المحاولة مرة أخرى.", language='ar')
        except sr.UnknownValueError:
            logger.warning("Language choice not understood.")
            speak("عذرًا، لم أفهم اللغة المختارة. يرجى المحاولة مرة أخرى.", language='ar')
        except sr.RequestError:
            logger.error("Error with speech recognition service.")
            speak("عذرًا، لم أفهم اللغة المختارة. يرجى المحاولة مرة أخرى.", language='ar')

# Modify the global status variable
status = "idle"  # Other possible statuses: "listening", "speaking", "standby"

def interact():
    """
    Handles the interaction with the user once the trigger word is detected.
    It includes language preference selection and ongoing conversation until an exit phrase is said.
    """
    preferred_language = ask_language_preference()  # Ask user for language preference
    if preferred_language == 'ar':
        global default_response
        default_response = "أنا آسف، ليس لدي إجابة على ذلك."
    else:
        default_response = "Je suis désolé, je n'ai pas de réponse à cela."

    chatbot.logic_adapters[0].default_response = default_response  # Update the default response
    language_code = "ar-AR" if preferred_language == 'ar' else "fr-FR"
    welcome_message = "مرحبا أنا النسخة الاولى من عُرِيفْ. كيف أستطيع مساعدتك؟" if preferred_language == 'ar' else "Bonjour, je suis Orriif. Comment puis-je vous aider aujourd'hui ?"
    speak(welcome_message, language=preferred_language)
    last_interaction_time = time.time()

    while True:
        logger.info("Listening for your question...")
        set_status("listening")
        audio = listen_for_audio()
        if audio is None:
            continue
        
        try:
            question = recognizer.recognize_google(audio, language=language_code)
            logger.info(f"You asked: {question}")

            # If the user says 'إلى اللقاء' or equivalent exit phrase, go into standby mode
            if question.lower() in ['bye', 'exit', 'quit', 'خروج', 'Au Revoir']:
                speak("الى اللقاء أتمنى أن تكون التجربة ممتعة و مفيدة !" if preferred_language == 'ar' else "Au revoir!", preferred_language)
                logger.info("User said 'إلى اللقاء', entering standby mode.")
                set_status("standby")  # Switch to standby mode
                return  # Exit the interact function to re-enter trigger listening mode

            response = get_response(question)
            logger.info(f"Response: {response}")

            speak(response, language=preferred_language)
            last_interaction_time = time.time()

        except sr.UnknownValueError:
            speak('عذرًا، لم أفهم ذلك.' if preferred_language == 'ar' else "Désolé, je n'ai pas compris cela.", preferred_language)
        except sr.RequestError:
            logger.error("Error with speech recognition service.")


def listen_for_trigger_and_interact():
    """
    This function listens for the trigger word continuously.
    When the trigger word is detected, it launches the interaction loop.
    """
    while True:
        set_status("standby")  # Chatbot enters standby mode, waiting for the trigger word
        logger.info("Chatbot is in standby mode, listening for the trigger word...")

        if listen_for_trigger():  # Wait for the trigger word
            logger.info("Trigger word detected! Launching interaction...")
            interact()  # Launch the interaction session once the trigger word is detected


def main():
    """
    The main function to start the chatbot system. It runs the Flask-SocketIO server
    on a separate thread and continuously listens for the trigger word.
    """
    from threading import Thread
    # Start the web server for Flask and SocketIO on a separate thread
    Thread(target=lambda: socketio.run(app, host='0.0.0.0', port=5000)).start()

    # Continuously listen for the trigger word and interact when detected
    listen_for_trigger_and_interact()


if __name__ == "__main__":
    main()
