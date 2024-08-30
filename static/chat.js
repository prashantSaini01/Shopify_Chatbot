document.addEventListener("DOMContentLoaded", function () {
    function sendMessage() {
        let message = document.getElementById("messageInput").value;
        console.log("Sending message:", message); 

        // Append the message to the chatbox immediately
        let chatboxMessage = document.querySelector(".chatbox-message");
        let messageContainer = document.createElement("div");
        messageContainer.classList.add("message-container", "my-2");
        messageContainer.innerHTML = `
            <div class="message-right sender">
                <div class="message-text">
                    <p>${message}</p>
                </div>
            </div>
        `;
        chatboxMessage.appendChild(messageContainer);

        // Clear input box
        document.getElementById("messageInput").value = "";

        // Scroll to bottom
        chatboxMessage.scrollTop = chatboxMessage.scrollHeight;

        // Show the "bot thinking" GIF
        let botThinking = document.createElement("div");
        botThinking.id = "botThinking";
        botThinking.classList.add("message-left", "receiver", "p-3");
        botThinking.innerHTML = `
            <img src="https://media2.giphy.com/media/20NLMBm0BkUOwNljwv/giphy.gif" alt="Bot is thinking..." class="small-gif">
        `;
        chatboxMessage.appendChild(botThinking);

        // Scroll to bottom
        chatboxMessage.scrollTop = chatboxMessage.scrollHeight;

        // Send AJAX request
        let xhr = new XMLHttpRequest();
        xhr.open("POST", "/send_message", true);
        xhr.setRequestHeader("Content-Type", "application/json;charset=UTF-8");

        xhr.onreadystatechange = function () {
            if (xhr.readyState === XMLHttpRequest.DONE) {
                if (xhr.status === 200) {
                    console.log("Response:", xhr.responseText); 

                    botThinking.remove();

                    const response = JSON.parse(xhr.responseText);
                    const htmlContent = marked.parse(response.reply);
                    console.log(htmlContent);

                    // Append the bot's response to the chatbox
                    let botMessageContainer = document.createElement("div");
                    botMessageContainer.classList.add("message-container", "my-2");
                    botMessageContainer.innerHTML = `
                        <div class="message-avatar">
                            <img src="https://img.freepik.com/free-vector/graident-ai-robot-vectorart_78370-4114.jpg?size=338&ext=jpg&ga=GA1.1.2082370165.1716422400&semt=ais_user" />
                        </div>
                        <div class="message-left receiver p-3">
                            <div class="message-text">                
                                <div class="card border-0">
                                    <div class="card-body">
                                        ${htmlContent}                                                
                                    </div>                                            
                                </div>
                                <button class="btn px-5 rounded-4 mt-3" onclick="resetChatEngine()">Reset Chat</button>                                                                                
                            </div>
                        </div>
                    `;
                    chatboxMessage.appendChild(botMessageContainer);
                    chatboxMessage.scrollTop = chatboxMessage.scrollHeight;
                } else {
                    console.error("Error:", xhr.status, xhr.statusText);
                    alert("Error sending message: " + xhr.responseText); 


                    botThinking.style.display = "none";
                }
            }
        };

        xhr.send(JSON.stringify({ message: message }));
    }

    document.getElementById("sendButton").addEventListener("click", function () {
        sendMessage();
    });

    document.getElementById("messageInput").addEventListener("keypress", function (event) {
        if (event.which == 13) {
            event.preventDefault();
            sendMessage();
        }
    });
});

function resetChatEngine() {
    fetch("/reset_chat_engine", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
    })
    .then((response) => response.json())
    .then((data) => {
        alert(data.reply);
        // Clear the chat-box
        document.querySelector(".chatbox-message").innerHTML = "";
    });
}
 