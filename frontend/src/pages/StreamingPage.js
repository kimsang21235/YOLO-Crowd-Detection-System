import React, { useState, useEffect, useMemo, useRef } from 'react';

// 백엔드 서버 주소
import { API_BASE_URL, WS_BASE_URL } from '../config';

// ===================================================================
//  이벤트 로그를 위한 자식 컴포넌트 (기존과 동일)
// ===================================================================
function EventLog({ activeStreamId }) {
    const [events, setEvents] = useState([]);
    const [modalVideo, setModalVideo] = useState(null);

    useEffect(() => {
        const fetchEvents = async () => {
            try {
                const response = await fetch(`${API_BASE_URL}/events/${activeStreamId}`);
                if (!response.ok) throw new Error('Network response was not ok');
                const data = await response.json();
                setEvents(data.slice(0, 5));
            } catch (error) {
                console.error(`Failed to fetch events for ${activeStreamId}:`, error);
                setEvents([]);
            }
        };

        fetchEvents();
        const intervalId = setInterval(fetchEvents, 5000);
        return () => clearInterval(intervalId);
    }, [activeStreamId]);

    const openModal = (videoUrl) => setModalVideo(videoUrl);
    const closeModal = () => setModalVideo(null);

    return (
        <>
            <div className="event-banner-container" style={{ flex: 1, background: '#f8f9fa', padding: '20px', borderRadius: '8px', height: 'fit-content' }}>
                <h4 style={{ marginTop: 0, borderBottom: '2px solid #dee2e6', paddingBottom: '10px' }}>이벤트 로그</h4>
                <div className="event-list" style={{ maxHeight: '600px', overflowY: 'auto' }}>
                    {events.length > 0 ? events.map(event => (
                        <div key={event.id} className="event-item" style={{ display: 'flex', alignItems: 'center', padding: '10px 0', borderBottom: '1px solid #e9ecef' }}>
                            {/* 썸네일 — 클릭 시 영상 모달 */}
                            <div
                                onClick={() => openModal(`${API_BASE_URL}${event.video_url}`)}
                                style={{ position: 'relative', width: '80px', height: '60px', marginRight: '15px', cursor: 'pointer', flexShrink: 0 }}
                            >
                                {event.thumbnail_url ? (
                                    <img
                                        src={`${API_BASE_URL}${event.thumbnail_url}`}
                                        alt={event.status}
                                        style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: '4px' }}
                                    />
                                ) : (
                                    <div style={{ width: '100%', height: '100%', background: '#343a40', borderRadius: '4px' }} />
                                )}
                                {/* 재생 버튼 오버레이 */}
                                <div style={{
                                    position: 'absolute', inset: 0, display: 'flex',
                                    alignItems: 'center', justifyContent: 'center',
                                    background: 'rgba(0,0,0,0.3)', borderRadius: '4px'
                                }}>
                                    <span style={{ color: '#fff', fontSize: '20px' }}>▶</span>
                                </div>
                            </div>
                            <div className="event-details">
                                <p style={{ margin: 0, fontWeight: '600', color: '#495057' }}>{event.status}</p>
                                <p style={{ margin: 0, fontSize: '0.85rem', color: '#6c757d' }}>{event.timestamp}</p>
                            </div>
                        </div>
                    )) : <p>발생한 이벤트가 없습니다.</p>}
                </div>
            </div>

            {/* 비디오 재생 모달 */}
            {modalVideo && (
                <div
                    onClick={closeModal}
                    style={{
                        position: 'fixed', inset: 0,
                        backgroundColor: 'rgba(0,0,0,0.85)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        zIndex: 1000,
                    }}
                >
                    <span
                        onClick={closeModal}
                        style={{ position: 'absolute', top: '20px', right: '35px', color: '#fff', fontSize: '40px', cursor: 'pointer' }}
                    >&times;</span>
                    <video
                        src={modalVideo}
                        controls
                        autoPlay
                        onClick={e => e.stopPropagation()}
                        style={{ maxWidth: '90%', maxHeight: '90vh', borderRadius: '8px' }}
                    />
                </div>
            )}
        </>
    );
}

// ===================================================================
//  메인 페이지 컴포넌트 (수정된 로직)
// ===================================================================
function StreamingPage() {
    const streamIds = ['stream1', 'stream2', 'stream3', 'stream4'];

    // 페이지 로드(새로고침) 시 모든 이벤트 이미지 삭제
    useEffect(() => {
        const cleanup = async () => {
            try {
                await fetch(`${API_BASE_URL}/admin/cleanup-events`, {
                    method: 'POST',
                    headers: { 'X-Cleanup-Secret': 'changeme' },
                });
            } catch (e) {
                console.warn('Cleanup failed:', e);
            }
        };
        cleanup();
    }, []); // 마운트 시 1회만 실행
    const [streamAnalysisTypes, setStreamAnalysisTypes] = useState(
        streamIds.reduce((acc, id) => {
            acc[id] = { count: true, mosaic: false, heatmap: false };
            return acc;
        }, {})
    );
    const [activeStreamId, setActiveStreamId] = useState('stream1');
    const canvasRef = useRef(null);
    const socketRef = useRef(null); // 웹소켓 객체를 저장하기 위한 Ref

    // 웹소켓 URL은 activeStreamId가 바뀔 때만 다시 계산
    const wsUrl = useMemo(() => {
        const initialTypes = Object.entries(streamAnalysisTypes[activeStreamId])
            .filter(([, isActive]) => isActive)
            .map(([type]) => type);
        const analysisQuery = initialTypes.join(',');
        return `${WS_BASE_URL}/ws/video_feed/${activeStreamId}?analysis=${analysisQuery}`;
    }, [activeStreamId]);

    // 웹소켓 연결 및 메시지 처리를 위한 useEffect
    // 이제 activeStreamId가 변경될 때만 웹소켓 연결을 새로 맺음
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const audio = new Audio('/sound.mp3');

        console.log(`Connecting to WebSocket: ${wsUrl}`);
        const socket = new WebSocket(wsUrl);
        socketRef.current = socket; // 소켓 객체를 ref에 저장

        socket.onopen = () => {
            console.log('WebSocket connection established.');
        };

        socket.onmessage = async (event) => {
            if (event.data instanceof Blob) {
                try {
                    const imageBitmap = await createImageBitmap(event.data);
                    ctx.drawImage(imageBitmap, 0, 0, canvas.width, canvas.height);
                } catch (e) {}
            } else if (typeof event.data === 'string' && event.data === 'PLAY_SOUND') {
                console.log('PLAY_SOUND signal received');
                audio.play().catch(error => console.error("Audio play failed:", error));
            }
        };

        socket.onclose = (event) => {
            console.log('WebSocket connection closed:', event);
        };

        socket.onerror = (error) => {
            console.error('WebSocket error:', error);
            socket.close();
        };

        // 컴포넌트 언마운트 또는 activeStreamId 변경 시 기존 연결 해제
        return () => {
            if (socketRef.current) {
                console.log('Closing WebSocket connection.');
                socketRef.current.close();
            }
        };
    }, [activeStreamId]); // wsUrl 대신 activeStreamId에만 의존

    // 분석 유형을 변경할 때 웹소켓으로 메시지를 보내는 함수
    const sendAnalysisUpdate = (streamId, types) => {
        if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
            const activeAnalyses = Object.entries(types[streamId])
                .filter(([, isActive]) => isActive)
                .map(([type]) => type);
            
            console.log('Sending analysis update:', activeAnalyses);
            socketRef.current.send(JSON.stringify({
                type: "update_analysis",
                payload: activeAnalyses
            }));
        }
    };

    // 분석 버튼 클릭 핸들러
    const handleStreamAnalysisChange = (streamId, analysisType) => {
        // 1. UI 상태를 먼저 업데이트
        const newTypes = {
            ...streamAnalysisTypes,
            [streamId]: {
                ...streamAnalysisTypes[streamId],
                [analysisType]: !streamAnalysisTypes[streamId][analysisType],
            },
        };
        setStreamAnalysisTypes(newTypes);
        
        // 2. 웹소켓 메시지로 백엔드에 변경 사항 알림
        sendAnalysisUpdate(streamId, newTypes);
    };

    return (
        <div className="page-container">
            <header>
                <h2>실시간 스트리밍 분석</h2>
            </header>

            <section className="analysis-section">
                <div className="home-layout-container" style={{ display: 'flex', gap: '20px' }}>
                    {/* --- Video Container (Left Column) --- */}
                    <div className="video-container" style={{ flex: 3 }}>
                        <div className="video-header">
                            <h3>카메라 {activeStreamId.replace('stream', '')}</h3>
                            <div className="video-controls">
                                <div className="camera-selection">
                                    <div className="stream-selector button-group">
                                        {streamIds.map(id => (
                                            <button 
                                                key={id}
                                                onClick={() => setActiveStreamId(id)}
                                                className={activeStreamId === id ? 'active' : ''}
                                            >
                                                카메라 {id.replace('stream', '')}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div className="video-wrapper">
                            <canvas 
                                ref={canvasRef} 
                                width="1280" 
                                height="720" 
                                className="stream-video"
                                style={{ width: '100%', backgroundColor: '#000' }}
                            />
                        </div>
                        <div className="button-group" style={{ marginTop: '20px' }}>
                            <button 
                                onClick={() => handleStreamAnalysisChange(activeStreamId, 'count')}
                                className={`count ${streamAnalysisTypes[activeStreamId]?.count ? 'active' : ''}`}>
                                인원 수
                            </button>
                            <button 
                                onClick={() => handleStreamAnalysisChange(activeStreamId, 'mosaic')}
                                className={`mosaic ${streamAnalysisTypes[activeStreamId]?.mosaic ? 'active' : ''}`}>
                                모자이크
                            </button>
                            <button 
                                onClick={() => handleStreamAnalysisChange(activeStreamId, 'heatmap')}
                                className={`heatmap ${streamAnalysisTypes[activeStreamId]?.heatmap ? 'active' : ''}`}>
                                핫플
                            </button>
                        </div>
                    </div>

                    {/* --- Event Log 컴포넌트 호출 --- */}
                    <EventLog activeStreamId={activeStreamId} />
                </div>
            </section>
        </div>
    );
}

export default StreamingPage;