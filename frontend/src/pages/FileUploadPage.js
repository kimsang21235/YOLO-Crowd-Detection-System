import React, { useState } from 'react';

// 백엔드 서버 주소 (App.js와 동일하게 사용)
import { API_BASE_URL } from '../config';

function FileUploadPage() {
    // --- 상태 관리 ---
    const [selectedFile, setSelectedFile] = useState(null);
    const [status, setStatus] = useState('idle'); // idle, loading, success, error
    const [resultVideoUrl, setResultVideoUrl] = useState('');
    const [errorMessage, setErrorMessage] = useState('');

    // --- 이벤트 핸들러 ---
    const handleFileChange = (event) => {
        setSelectedFile(event.target.files[0]);
        setResultVideoUrl('');
        setStatus('idle');
    };

    const handleAnalyze = async (isAnonymize, isVisualize) => {
        if (!selectedFile) {
            alert('분석할 동영상 파일을 선택해주세요.');
            return;
        }

        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('anonymize', isAnonymize);
        formData.append('visualize', isVisualize);

        setStatus('loading');
        setErrorMessage('');

        try {
            const response = await fetch(`${API_BASE_URL}/process-video`, {
                method: 'POST',
                body: formData,
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || '서버에서 오류가 발생했습니다.');
            }

            const fullVideoUrl = `${API_BASE_URL}${data.processed_video_url}`;
            setResultVideoUrl(fullVideoUrl);
            setStatus('success');

        } catch (error) {
            console.error('분석 중 오류 발생:', error);
            setErrorMessage(error.message);
            setStatus('error');
        }
    };

    // --- 렌더링 로직 ---
    const getStatusMessage = () => {
        switch (status) {
            case 'loading':
                return <p className="status-message loading">AI가 영상을 분석 중입니다... 잠시만 기다려주세요.</p>;
            case 'error':
                return <p className="status-message error">오류가 발생했습니다: {errorMessage}</p>;
            case 'success':
                return <p className="status-message success">영상 분석이 완료되었습니다!</p>;
            default:
                return null;
        }
    };

    return (
        <div className="page-container">
            <header>
                <h2>동영상 파일 분석</h2>
            </header>

            <section className="analysis-section">
                <div className="upload-section">
                    <input type="file" accept="video/*" onChange={handleFileChange} />
                    <div className="button-group">
                        <button 
                            className="analyze-button mosaic" 
                            onClick={() => handleAnalyze(true, false)} 
                            disabled={!selectedFile || status === 'loading'}
                        >
                            {status === 'loading' ? '처리 중...' : '모자이크'}
                        </button>
                        <button 
                            className="analyze-button tracking" 
                            onClick={() => handleAnalyze(false, true)} 
                            disabled={!selectedFile || status === 'loading'}
                        >
                            {status === 'loading' ? '처리 중...' : '객체 동선 추적'}
                        </button>
                    </div>
                </div>

                {getStatusMessage()}

                {status === 'success' && resultVideoUrl && (
                    <div className="result-section">
                        <h3>분석 결과 영상</h3>
                        <video className="result-video" src={resultVideoUrl} controls autoPlay loop>
                            브라우저가 비디오 태그를 지원하지 않습니다.
                        </video>
                    </div>
                )}
            </section>
        </div>
    );
}

export default FileUploadPage;
