import React, { useState, useRef, useEffect } from "react";
import SimplePeer from "simple-peer";

function App() {
  const [name, setName] = useState("");
  const [registered, setRegistered] = useState(false);
  const [roomCode, setRoomCode] = useState("");
  const [peerName, setPeerName] = useState("");
  const [isInitiator, setIsInitiator] = useState(null);
  const [status, setStatus] = useState("idle");
  
  const matchWsRef = useRef(null);
  const signalWsRef = useRef(null);
  const localVideoRef = useRef(null);
  const remoteVideoRef = useRef(null);
  const peerRef = useRef(null);
  const localStreamRef = useRef(null);
  const initiatorFlagRef = useRef(null); // Use ref to avoid race conditions

  function openSignalingWS(username) {
    if (signalWsRef.current) return;
    
    const ws = new WebSocket(`ws://localhost:4000/ws/${encodeURIComponent(username)}`);
    
    ws.onopen = () => {
      console.log("[sigws] connected");
    };
    
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        handleSignalMessage(msg);
      } catch (e) {
        console.error("Invalid JSON on signaling ws:", ev.data);
      }
    };
    
    ws.onclose = () => {
      console.log("[sigws] closed");
    };
    
    ws.onerror = (e) => console.error("[sigws] err", e);
    
    signalWsRef.current = ws;
  }

  function handleSignalMessage(msg) {
    if (!msg || !msg.event) return;
    
    if (msg.event === "verified") {
      console.log("[sigws] verified", msg);
      setStatus("verified");
    }
    
    if (msg.event === "signal") {
      // Only create peer if we're the non-initiator AND peer doesn't exist yet
      if (!peerRef.current && !initiatorFlagRef.current) {
        console.log("[sigws] Creating peer as responder (receiving first signal)");
        const peerObj = new SimplePeer({
          initiator: false,
          trickle: true,
          stream: localStreamRef.current
        });
        
        peerObj.on("signal", (data) => {
          if (signalWsRef.current && signalWsRef.current.readyState === WebSocket.OPEN) {
            signalWsRef.current.send(JSON.stringify({
              event: "signal",
              room_code: msg.room_code,
              target: msg.from,
              type: "signal",
              data
            }));
          }
        });
        
        peerObj.on("stream", (remoteStream) => {
          console.log("[peer] Received remote stream");
          if (remoteVideoRef.current) {
            remoteVideoRef.current.srcObject = remoteStream;
          }
        });
        
        peerObj.on("error", (err) => console.error("[peer] error:", err));
        peerObj.on("close", () => console.log("[peer] closed"));
        
        peerRef.current = peerObj;
      }
      
      // Signal the peer with incoming data
      if (peerRef.current) {
        try {
          peerRef.current.signal(msg.data);
        } catch (e) {
          console.error("[peer] signal error:", e);
        }
      }
    }
    
    if (msg.event === "error") {
      console.error("Signaling error:", msg.message || msg);
      setStatus("error: " + (msg.message || "unknown"));
    }
    
    if (msg.event === "peer-disconnected") {
      setStatus("peer-disconnected");
      if (peerRef.current) {
        peerRef.current.destroy();
        peerRef.current = null;
      }
    }
  }

  function openMatchingWS(username) {
    if (matchWsRef.current) return;
    
    const ws = new WebSocket(`ws://localhost:8000/ws/${encodeURIComponent(username)}`);
    
    ws.onopen = () => {
      console.log("[matchws] connected");
    };
    
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        
        if (msg.event === "matched") {
          console.log("[matchws] matched", msg);
          const rc = msg.room_code;
          const initiator = Boolean(msg.initiator);
          
          setRoomCode(rc);
          const parts = rc.split("_");
          const peer = parts.find((p) => p !== username) || "";
          setPeerName(peer);
          setIsInitiator(initiator);
          initiatorFlagRef.current = initiator; // Store in ref immediately
          setStatus("matched");

          openSignalingWS(username);
          
          const waitForSig = setInterval(() => {
            if (signalWsRef.current && signalWsRef.current.readyState === WebSocket.OPEN) {
              clearInterval(waitForSig);
              
              signalWsRef.current.send(JSON.stringify({
                event: "join",
                room_code: rc,
                target: peer,
                type: initiator ? "offer" : "answer"
              }));
              
              startWebRTC(initiator, rc, peer);
            }
          }, 100);
        } else {
          console.log("[matchws] msg", msg);
        }
      } catch (e) {
        console.error("[matchws] bad message", ev.data);
      }
    };
    
    ws.onclose = () => {
      console.log("[matchws] closed");
    };
    
    ws.onerror = (e) => console.error("[matchws] err", e);
    
    matchWsRef.current = ws;
  }

  async function register() {
    if (!name) return alert("Enter a name");
    
    try {
      openMatchingWS(name);
      
      const resp = await fetch("http://localhost:8000/registerForMatching", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name })
      });
      
      const body = await resp.json();
      console.log("register resp:", body);
      setRegistered(true);
      setStatus("queued");
    } catch (e) {
      console.error("Register failed", e);
      setStatus("register-failed");
    }
  }

  async function startWebRTC(initiatorFlag, room_code, peer) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        video: true, 
        audio: true 
      });
      
      localVideoRef.current.srcObject = stream;
      localStreamRef.current = stream; // FIX: Store stream in ref
      
      // Only create peer if initiator (responder creates on first signal)
      if (initiatorFlag) {
        console.log("[webrtc] Creating peer as initiator");
        const peerObj = new SimplePeer({
          initiator: true,
          trickle: true,
          stream
        });
        
        peerObj.on("signal", (data) => {
          if (signalWsRef.current && signalWsRef.current.readyState === WebSocket.OPEN) {
            signalWsRef.current.send(JSON.stringify({
              event: "signal",
              room_code,
              target: peer,
              type: "signal",
              data
            }));
          }
        });
        
        peerObj.on("stream", (remoteStream) => {
          console.log("[peer] Received remote stream");
          if (remoteVideoRef.current) {
            remoteVideoRef.current.srcObject = remoteStream;
          }
        });
        
        peerObj.on("error", (err) => console.error("[peer] error:", err));
        peerObj.on("close", () => console.log("[peer] closed"));
        
        peerRef.current = peerObj;
      }
    } catch (e) {
      console.error("getUserMedia failed:", e);
      setStatus("media-error: " + e.message);
    }
  }

  useEffect(() => {
    return () => {
      try {
        if (matchWsRef.current) matchWsRef.current.close();
        if (signalWsRef.current) signalWsRef.current.close();
        if (peerRef.current) peerRef.current.destroy();
        if (localStreamRef.current) {
          localStreamRef.current.getTracks().forEach((t) => t.stop());
        }
      } catch (e) {
        console.error("Cleanup error:", e);
      }
    };
  }, []);

  return (
    <div style={{ padding: 20, fontFamily: "sans-serif" }}>
      <h1>Mini Omegle (React)</h1>
      {!registered ? (
        <div>
          <input
            placeholder="Your name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ padding: 8, marginRight: 8 }}
          />
          <button onClick={register}>Register & Start Matching</button>
        </div>
      ) : (
        <div>
          <p><strong>Name:</strong> {name}</p>
          <p><strong>Status:</strong> {status}</p>
          <p><strong>Room:</strong> {roomCode || "-"}</p>
          <p><strong>Peer:</strong> {peerName || "-"}</p>
          <p><strong>Role:</strong> {isInitiator === null ? "-" : isInitiator ? "initiator" : "responder"}</p>
          
          <div style={{ display: "flex", gap: 20, marginTop: 20 }}>
            <div>
              <h3>Local</h3>
              <video
                ref={localVideoRef}
                autoPlay
                playsInline
                muted
                style={{ width: 320, height: 240, background: "#000" }}
              />
            </div>
            <div>
              <h3>Remote</h3>
              <video
                ref={remoteVideoRef}
                autoPlay
                playsInline
                style={{ width: 320, height: 240, background: "#000" }}
              />
            </div>
          </div>
        </div>
      )}
      <p style={{ marginTop: 20, fontSize: 12, color: "#666" }}>
        Make sure matching service runs at `http://localhost:8000` and signaling at `http://localhost:4000`.
        <br />
        Open two browser tabs (different names) to test.
      </p>
    </div>
  );
}

export default App;