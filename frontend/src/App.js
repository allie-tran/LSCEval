import React, { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import "./App.css";

const FIXED_TIME = 30 * 1000;

const App = () => {
  const [query, setQuery] = useState("Waiting to start.");
//   const [time, setTime] = useState(0);
  const [realTime, setRealTime] = useState(0);
  const [pause, setPause] = useState(false);
  const [sessionId, setSessionId] = useState("Session ID");
  const [score, setScore] = useState(0);
  const [totalScore, setTotalScore] = useState(0);
  const [hiddenQuery, setHiddenQuery] = useState("");
  const [end, setEnd] = useState(null)
  
  const handleChange = (event) => {
    setSessionId(event.target.value);
  };

  const handleSubmit = (event) => {
    const response = axios.get(
      "https://mysceal-eval.computing.dcu.ie/be/?session_name=" + sessionId,
      {
        headers: { "Content-Type": "text/plain" },
      }
    );
    response.then((res) => {
      if (res.data.query !== "The End.") {
        setEnd(Date.now() + FIXED_TIME);
        setRealTime(FIXED_TIME / 1000);
      }
      setQuery(res.data.query);
      setScore(res.data.score);
      setTotalScore(res.data.total_score);
    });
    event.preventDefault();
  };

  const handleContinue = (event) => {
    setPause(false);
  };

  useEffect(() => {
    let myInterval = setInterval(() => {
      if (realTime > 0) {
        setRealTime((end - Date.now()) / 1000);
        if (query !== "The End." && query !== "Waiting to start.") {
          const response = axios.get(
            "https://mysceal-eval.computing.dcu.ie/be/get_score?session_name=" +
              sessionId +
              "&time=" +
              realTime,
            {
              headers: { "Content-Type": "text/plain" },
            }
          );
          response.then((res) => {
            setScore(res.data.score);
            setTotalScore(res.data.total_score);
          });
        }
      } 
       if (Math.floor(realTime) === 0) {
        if (query !== "The End." && query !== "Waiting to start.") {
          const response = axios.get(
            "https://mysceal-eval.computing.dcu.ie/be/next_clue?session_name=" +
              sessionId,
            {
              headers: { "Content-Type": "text/plain" },
            }
          );
          response.then((res) => {
            setScore(res.data.score);
            setTotalScore(res.data.total_score);
            
            if (res.data.new) {
              setEnd(Date.now() - 1000);
              setPause(true);
              setHiddenQuery(res.data.query);
            } else {
              console.log(res.data.query);
              setQuery(res.data.query);
              if (res.data.query === "The End.") {
                setEnd(Date.now() - 1000);
                setRealTime(0)
              }
              else {
                setEnd(Date.now() + res.data.time * 1000);
                setRealTime(res.data.time);
              }
            }
          });
        }
      }  
      if (realTime < 0) {
        if (!pause) {
          setQuery(hiddenQuery);
          setEnd(
            hiddenQuery === "The End."
              ? Date.now() - 1000
              : Date.now() + FIXED_TIME
          );
          setRealTime(FIXED_TIME / 1000);
        }
      }
    }, 500);
    return () => {
      clearInterval(myInterval);
    };
  }, [query, realTime, score, pause, hiddenQuery, end, sessionId]);

  return (
    <div className="App">
      <form onSubmit={handleSubmit}>
        <label>
          Session ID
          <input type="text" value={sessionId} onChange={handleChange} />
        </label>
        <input type="submit" value="Submit" />
      </form>
      <header className="App-header">
        <pre className="text">{query}</pre>
        <p className="text">Time: {Math.floor(realTime)}s</p>
        <p className="text">Score: {score}</p>
        <p className="text">Total: {totalScore}</p>
        {pause ? (
          <form onSubmit={handleContinue}>
            <input type="submit" value={"Continue"} />
          </form>
        ) : null}
      </header>
    </div>
  );
};

export default App;
