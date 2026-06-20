import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import HomeScreen from "./screens/HomeScreen";
import CameraScreen from "./screens/CameraScreen";
import ResultsScreen from "./screens/ResultsScreen";
import "./App.css";

function App() {
  return (
    <div className="bg-[#0A0A0A] min-h-screen">
      <BrowserRouter>
        <div className="max-w-md mx-auto min-h-screen relative overflow-x-hidden">
          <Routes>
            <Route path="/" element={<HomeScreen />} />
            <Route path="/camera" element={<CameraScreen />} />
            <Route path="/results" element={<ResultsScreen />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </BrowserRouter>
    </div>
  );
}

export default App;
