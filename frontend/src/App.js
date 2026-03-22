import React from 'react';
import { Routes, Route } from 'react-router-dom';
import Navbar from './components/Navbar';
import FileUploadPage from './pages/FileUploadPage';
import StreamingPage from './pages/StreamingPage';
import './App.css';

function App() {
    return (
        <div className="container">
            <Navbar />
            <main className="main-content">
                <Routes>
                    <Route path="/" element={<FileUploadPage />} />
                    <Route path="/streaming" element={<StreamingPage />} />
                </Routes>
            </main>
        </div>
    );
}

export default App;