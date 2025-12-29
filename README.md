# Real-Time Random Video Chat Platform

This project is a **real-time random video chat system** built using a **Matching Server** and a **Signalling Server**, enabling users to get randomly paired and connect via **WebRTC** for video calls and chat.

---

## System Architecture Overview

The system is divided into **two independent backend services**:

1. Matching Server  
2. Signalling Server  

Each component has a clearly defined responsibility to keep the architecture scalable and maintainable.

---

## Matching Server

### Purpose
The Matching Server is responsible for **pairing users randomly** and assigning them a shared room.

### Responsibilities
- Accepts **register requests** from users.
- Pushes users into a **Redis-based matching queue**.
- Continuously polls the Redis queue:
  - Uses an **exponential backoff strategy** when fewer than two users are available.
- Randomly selects **two users** from the queue.
- Generates a **unique room code** for the matched pair.
- Notifies both users of the room code via **WebSocket connections**.

### Key Features
- Redis-backed queue for fast operations  
- Efficient backoff to reduce CPU usage  
- Decoupled from WebRTC logic  
- Scales independently  

---

## Signalling Server

### Purpose
The Signalling Server handles **WebRTC session setup** and **real-time messaging**.

### Responsibilities
- Acts as a **WebRTC signalling server**
- Handles:
  - Offer / Answer exchange
  - ICE candidate exchange
- Manages **WebSocket-based chat**
- Uses the **room code** received from the Matching Server to connect users

### Key Features
- WebRTC-compatible signalling flow  
- WebSocket-based messaging  
- Stateless room handling  
- Low latency communication  

---

## Communication Flow

1. User connects to the **Matching Server**
2. User is added to the Redis queue
3. Two users are matched
4. Both users receive a **room code**
5. Users connect to the **Signalling Server** using the room code
6. WebRTC peer connection is established
7. Video call and chat begin

---

## Tech Stack

### Backend
- Node.js / Python  
- Redis (Queue and State)  
- WebSockets  
- WebRTC  

### Frontend
- React  
- WebRTC APIs  
- WebSocket Client  

---

## Frontend Repository

Frontend GitHub Repository:  

https://github.com/armangupta910/Random-Video-Chat-Frontend?tab=readme-ov-file

---

## Future Improvements
- Matchmaking filters (region, language, interests)
- Moderation and reporting
- Reconnect logic
- TURN server support
- Rate limiting and abuse prevention

---

## License
MIT License

---

## Contributing
Pull requests are welcome.  
Feel free to open issues for bugs or feature requests.
