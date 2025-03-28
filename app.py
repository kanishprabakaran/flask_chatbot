import os
import logging
from typing import Dict, Any
from pydantic import BaseModel, Field
from langchain.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, AIMessage
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_google_genai import ChatGoogleGenerativeAI
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import requests  # Add this import

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)

# Get API key from environment variable
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("No Google API Key found. Please set the GOOGLE_API_KEY environment variable.")

# Set the environment variable for the Google API
os.environ["GOOGLE_API_KEY"] = api_key

# Initialize Gemini AI client
genai_client = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0.7)

# Define the output structures using Pydantic
class ThirukkuralResponse(BaseModel):
    verse: str = Field(description="The original Thirukkural verse in Tamil")
    translation: str = Field(description="English translation of the Thirukkural")
    section: str = Field(description="The section name the Thirukkural belongs to (Aram, Porul, or Inbam)")
    explanation: str = Field(description="Detailed explanation of the Thirukkural's meaning and significance")
    story: str = Field(description="A short story or anecdote that illustrates the meaning of this Thirukkural")

class BhagavadGitaResponse(BaseModel):
    verse: str = Field(description="The original Bhagavad Gita verse in Sanskrit")
    translation: str = Field(description="English translation of the verse")
    chapter: str = Field(description="The chapter and verse number")
    explanation: str = Field(description="Detailed explanation of the verse's meaning and significance")
    story: str = Field(description="A short story or anecdote that illustrates the meaning of this verse")

# Create the LangChain parsers
thirukkural_parser = PydanticOutputParser(pydantic_object=ThirukkuralResponse)
gita_parser = PydanticOutputParser(pydantic_object=BhagavadGitaResponse)

# Define the prompt templates
thirukkural_template = """
You are a Thirukkural expert. Find the most relevant Thirukkural based on the user's query and the conversation context.

The user is asking about: {query}

Previous conversation context: 
{chat_history}

IMPORTANT INSTRUCTIONS:
1. Based on the query and previous conversation, find a Thirukkural that best matches the user's intent.
2. If the user's query seems to build on previous questions, provide a Thirukkural that relates to both the current query AND previous conversation.
3. If the user asks for "another one" or "similar" or uses other referential language, understand they want a different Thirukkural on the same topic discussed previously.
4. Create a short engaging story (200-300 words) that illustrates the moral or lesson of this Thirukkural in a modern context.

Return your response in the following JSON format:
{format_instructions}
"""

bhagavad_gita_template = """
You are a Bhagavad Gita expert. Find the most relevant verse from the Bhagavad Gita based on the user's query and the conversation context.

The user is asking about: {query}

Previous conversation context: 
{chat_history}

IMPORTANT INSTRUCTIONS:
1. Based on the query and previous conversation, find a verse from the Bhagavad Gita that best matches the user's intent.
2. If the user's query seems to build on previous questions, provide a verse that relates to both the current query AND previous conversation.
3. If the user asks for "another one" or "similar" or uses other referential language, understand they want a different verse on the same topic discussed previously.
4. Create a short engaging story (200-300 words) that illustrates the message or lesson of this verse in a modern context.

Return your response in the following JSON format:
{format_instructions}
"""

# Setup the prompts with the parsers
thirukkural_prompt = PromptTemplate(
    template=thirukkural_template,
    input_variables=["query", "chat_history"],
    partial_variables={"format_instructions": thirukkural_parser.get_format_instructions()},
)

bhagavad_gita_prompt = PromptTemplate(
    template=bhagavad_gita_template,
    input_variables=["query", "chat_history"],
    partial_variables={"format_instructions": gita_parser.get_format_instructions()},
)

# Initialize message histories
thirukkural_history = ChatMessageHistory()
bhagavad_gita_history = ChatMessageHistory()

# Function to convert message history to formatted string
def format_chat_history(history, max_messages=10):
    messages = history.messages[-max_messages:]  # Limit to last 10 messages
    return "\n".join(f"{'User' if isinstance(msg, HumanMessage) else 'Assistant'}: {msg.content}" for msg in messages)

# Function to determine the text type based on the query
def determine_text_type(query: str) -> str:
    query_lower = query.lower()
    
    # Keywords for Thirukkural
    thirukkural_keywords = ["thirukkural", "kural", "tamil", "aram", "porul", "inbam"]
    
    # Keywords for Bhagavad Gita
    gita_keywords = ["bhagavad gita", "gita", "krishna", "arjuna", "yoga", "dharma"]
    
    # Check for Thirukkural keywords
    if any(keyword in query_lower for keyword in thirukkural_keywords):
        return "thirukkural"
    
    # Check for Bhagavad Gita keywords
    elif any(keyword in query_lower for keyword in gita_keywords):
        return "bhagavad_gita"
    
    # Default to Thirukkural if no specific text is mentioned
    else:
        return "thirukkural"

# Function to generate response based on text type
def generate_response(query: str, text_type: str) -> Dict[str, Any]:
    try:
        if text_type == "thirukkural":
            chat_history = format_chat_history(thirukkural_history)
            formatted_prompt = thirukkural_prompt.format(query=query, chat_history=chat_history)
            response = genai_client.invoke(formatted_prompt)
            parsed_response = thirukkural_parser.parse(response.content)
            result_summary = f"Thirukkural about {parsed_response.section.lower()} - Translation: {parsed_response.translation}"
            thirukkural_history.add_user_message(query)
            thirukkural_history.add_ai_message(result_summary)
            generated_response = parsed_response.dict()
        else:
            chat_history = format_chat_history(bhagavad_gita_history)
            formatted_prompt = bhagavad_gita_prompt.format(query=query, chat_history=chat_history)
            response = genai_client.invoke(formatted_prompt)
            parsed_response = gita_parser.parse(response.content)
            result_summary = f"Bhagavad Gita {parsed_response.chapter} - Translation: {parsed_response.translation}"
            bhagavad_gita_history.add_user_message(query)
            bhagavad_gita_history.add_ai_message(result_summary)
            generated_response = parsed_response.dict()

        # Translate the generated response into supported languages
        translations = {}
        for lang in ["ta", "hi", "ml", "te", "bn", "gu", "kn", "mr", "pa", "ur"]:  # Add new languages here
            try:
                translations[lang] = {
                    "translation": translate_text(generated_response["translation"], lang),
                    "explanation": translate_text(generated_response["explanation"], lang),
                    "story": translate_text(generated_response["story"], lang),
                }
            except Exception as e:
                logging.error(f"Error translating to {lang}: {e}")
                translations[lang] = {
                    "translation": "Translation failed.",
                    "explanation": "Translation failed.",
                    "story": "Translation failed.",
                }

        # Add translations to the response
        generated_response["translations"] = translations
        return generated_response

    except Exception as e:
        logging.error(f"Error generating response: {e}")
        return {
            "verse": "Error",
            "translation": "Error",
            "section": "Error",
            "explanation": f"An error occurred: {str(e)}",
            "story": "Unable to generate a story at this time.",
            "translations": {}
        }

# Handle follow-up query dynamically for both Thirukkural and Bhagavad Gita
def is_follow_up_query(query: str) -> bool:
    """
    Determine if the query is a follow-up request for either Thirukkural or Bhagavad Gita.
    """
    query_lower = query.lower()
    # Check if the query is short and contains keywords related to Thirukkural or Bhagavad Gita
    return (
        len(query_lower.split()) <= 5 and  # Short query
        any(keyword in query_lower for keyword in ["thirukkural", "kural", "bhagavad gita", "gita", "similar", "same"])
    )

# Function to translate text using Azure Translator API
def translate_text(text: str, target_language: str) -> str:
    """
    Translates the given text into the target language using Azure Translator API.
    """
    translator_key = os.getenv("AZURE_TRANSLATOR_KEY")
    translator_endpoint = os.getenv("AZURE_TRANSLATOR_ENDPOINT")

    if not translator_key or not translator_endpoint:
        raise ValueError("Azure Translator API key or endpoint is not set in the environment variables.")

    # Azure Translator API URL
    url = f"{translator_endpoint}/translate?api-version=3.0&to={target_language}"

    # Headers for the API request
    headers = {
        "Ocp-Apim-Subscription-Key": translator_key,
        "Ocp-Apim-Subscription-Region": "centralindia",  # Replace with your Azure region if needed
        "Content-Type": "application/json"
    }

    # Request body
    body = [{"text": text}]

    # Make the API request
    response = requests.post(url, headers=headers, json=body)
    if response.status_code != 200:
        raise Exception(f"Azure Translator API error: {response.status_code} - {response.text}")

    # Parse the response
    translated_text = response.json()[0]["translations"][0]["text"]
    return translated_text

# Initialize Flask app
app = Flask(__name__)

# Route for handling queries
@app.route("/query", methods=["POST"])
def handle_query():
    data = request.json
    query = data.get("query")
    if not query:
        return jsonify({"error": "Query is required"}), 400

    # Handle introductory chat inputs
    if query.lower() in ["hi", "hello", "hey", "hi there", "hello there"]:
        return jsonify({
            "verse": "Greeting",
            "translation": "Hello! I'm a sacred text chatbot. How can I assist you today?",
            "section": "Greeting",
            "explanation": "This is a friendly greeting to start the conversation.",
            "story": "No story here, just a warm welcome!",
            "languages": ["ta", "hi", "ml", "te", "bn", "gu", "kn", "mr", "pa", "ur"],  # Add new languages here
            "ready_for_translation": True  # Indicate that translation options should be shown
        })

    text_type = determine_text_type(query)

    # Handle follow-up query dynamically
    if is_follow_up_query(query):
        if "thirukkural" in query.lower() or "kural" in query.lower():
            text_type = "thirukkural"
            last_query = bhagavad_gita_history.messages[-2].content if len(bhagavad_gita_history.messages) >= 2 else ""
        else:
            text_type = "bhagavad_gita"
            last_query = thirukkural_history.messages[-2].content if len(thirukkural_history.messages) >= 2 else ""

        query = f"{last_query} (in {text_type.replace('_', ' ').title()})"

    response = generate_response(query, text_type)

    # Add translation options to the response
    response["languages"] = ["ta", "hi", "ml", "te", "bn", "gu", "kn", "mr", "pa", "ur"]  # Add new languages here
    response["ready_for_translation"] = True  # Indicate that translation options should be shown

    return jsonify(response)

# Route to handle translation requests
@app.route("/translate", methods=["POST"])
def handle_translation():
    data = request.json
    text = data.get("text")
    explanation = data.get("explanation")
    story = data.get("story")
    target_language = data.get("language")

    if not text or not explanation or not story or not target_language:
        return jsonify({"error": "Text, explanation, story, and target language are required"}), 400

    try:
        translated_text = translate_text(text, target_language)
        translated_explanation = translate_text(explanation, target_language)
        translated_story = translate_text(story, target_language)

        return jsonify({
            "translated_text": translated_text,
            "translated_explanation": translated_explanation,
            "translated_story": translated_story,
            "languages": ["ta", "hi", "ml", "te", "bn", "gu", "kn", "mr", "pa", "ur"],  # Add new languages here
            "ready_for_translation": True  # Indicate that translation options should be shown again
        })
    except Exception as e:
        logging.error(f"Error during translation: {e}")
        return jsonify({"error": str(e)}), 500

# Route for clearing conversation history
@app.route("/clear_history", methods=["POST"])
def clear_history():
    thirukkural_history.clear()
    bhagavad_gita_history.clear()
    return jsonify({"message": "Conversation history cleared!"})

@app.route("/")
def home():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)