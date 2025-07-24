document.addEventListener('DOMContentLoaded', () => {
    const chatMessages = document.getElementById('chat-messages');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');
    const typingIndicator = document.querySelector('.typing-indicator');
    const micButton = document.getElementById('mic-button'); // NEW: Microphone button reference

    // --- Speech Recognition (Voice Input) Setup ---
    // Check for browser compatibility
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recognition = null; // Initialize recognition object

    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.continuous = false; // Stop listening after a single utterance
        recognition.interimResults = false; // Only return final results
        recognition.lang = 'en-US'; // Set language

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            userInput.value = transcript; // Put recognized text into input field
            sendMessage(true); // Send message (true indicates it came from voice)
        };

        recognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error);
            micButton.classList.remove('listening');
            let errorMessage = 'Could not understand voice input. Please try again or type your message.';
            if (event.error === 'not-allowed' || event.error === 'permission-denied') {
                errorMessage = 'Microphone access denied. Please allow microphone usage in your browser settings.';
            } else if (event.error === 'no-speech') {
                errorMessage = 'No speech detected. Please speak clearly.';
            }
            addMessage(errorMessage, 'bot');
        };

        recognition.onend = () => {
            micButton.classList.remove('listening'); // Remove listening indicator when done
        };

        micButton.addEventListener('click', () => {
            if (micButton.classList.contains('listening')) {
                recognition.stop();
            } else {
                micButton.classList.add('listening');
                userInput.value = ''; // Clear input before listening
                addMessage('Listening...', 'user-listening-message'); // Optional: show listening status
                recognition.start();
            }
        });
    } else {
        // Browser does not support Web Speech API
        console.warn('Web Speech API (SpeechRecognition) not supported in this browser.');
        micButton.style.display = 'none'; // Hide mic button if not supported
    }

    // --- Speech Synthesis (Voice Output) Setup ---
    const synth = window.speechSynthesis;
    let currentUtterance = null; // To keep track of the current speech

    function speakMessage(text) {
        if (!synth) {
            console.warn('Web Speech API (SpeechSynthesis) not supported in this browser.');
            return;
        }
        if (currentUtterance && synth.speaking) {
            synth.cancel(); // Stop current speech if any
        }

        currentUtterance = new SpeechSynthesisUtterance(text);
        currentUtterance.lang = 'en-US'; // Set language
        currentUtterance.pitch = 1; // 0 to 2
        currentUtterance.rate = 1;  // 0.1 to 10

        synth.speak(currentUtterance);
    }

    // Function to add a message to the chat display (modified to remove listening message)
    function addMessage(message, sender) {
        // Remove "Listening..." message if it's the next message from bot
        if (sender !== 'user-listening-message') {
            const listeningMessage = document.querySelector('.user-listening-message');
            if (listeningMessage) {
                listeningMessage.remove();
            }
        }

        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message');
        messageDiv.classList.add(`${sender}-message`);
        messageDiv.innerHTML =` <p>${message}</p>`;
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // NEW: Optional CSS for the listening message (add to style.css if you want it styled)
    // .user-listening-message {
    //     background-color: #f0f0f0;
    //     color: #555;
    //     align-self: flex-end;
    //     font-style: italic;
    // }


    // Function to control typing indicator
    function showTypingIndicator() {
        typingIndicator.style.display = 'flex';
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function hideTypingIndicator() {
        typingIndicator.style.display = 'none';
    }

    // Function to handle sending a message (modified to accept voice input flag)
    function sendMessage(isVoiceInput = false) { // isVoiceInput is new parameter
        const message = userInput.value.trim();
        if (message === '') return;

        // Only add user message if it's not from voice input (as voice recognition already puts it in input)
        if (!isVoiceInput) {
            addMessage(message, 'user');
        }

        userInput.value = ''; // Clear the input field after sending

        showTypingIndicator();

        fetch('http://127.0.0.1:5000/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message: message })
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(errorData => {
                    throw new Error(`Backend Error: ${response.status} - ${errorData.response || 'Unknown error'}`);
                });
            }
            return response.json();
        })
        .then(data => {
            hideTypingIndicator();
            addMessage(data.response, 'bot');
            speakMessage(data.response); // NEW: Speak the bot's response!

            // Update background (existing logic)
            const body = document.body;
            const currentCategory = data.weather_category;
            body.classList.remove('weather-clear', 'weather-clouds', 'weather-rain', 'weather-snow', 'weather-thunderstorm', 'weather-atmosphere', 'default-weather');
            if (currentCategory) {
                body.classList.add(`weather-${currentCategory}`);
            } else {
                body.classList.add('default-weather');
            }
        })
        .catch(error => {
            hideTypingIndicator();
            console.error('Error sending message to backend:', error);
            let errorMessage = 'Oops! The bot is having trouble. Please check your internet connection.';

            if (error.message.includes('Failed to fetch')) {
                errorMessage = 'The bot seems to be offline or unreachable. Please ensure the backend server is running.';
            } else if (error.message.includes('Backend Error: 500')) {
                errorMessage = 'There\'s an internal server error. Check your backend terminal for details.';
            } else if (error.message.includes('Backend Error: 400')) {
                errorMessage = 'The bot received a bad request. Perhaps your message was empty?';
            } else if (error.message.includes('Backend Error: 404')) {
                errorMessage = 'The bot couldn\'t find that resource. (This might indicate an issue with a valid city name)';
            } else if (error.message.includes('Backend Error:')) {
                errorMessage = ` A backend error occurred: ${error.message.split('Backend Error: ')[1].substring(0, 100)}`;
            }

            addMessage(errorMessage, 'bot');
            speakMessage(errorMessage); // NEW: Speak the error message
        });
    }

    // Event listener for the send button click
    sendButton.addEventListener('click', () => sendMessage(false)); // False indicates typed input

    // Event listener for pressing Enter key in the input field
    userInput.addEventListener('keypress', (event) => {
        if (event.key === 'Enter') {
            sendMessage(false); // False indicates typed input
            event.preventDefault();
        }
    });
});