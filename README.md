# 🌟 Video Crowd Monitoring (Refactored Portfolio Version)

> **본 레포지토리는 팀 프로젝트 결과물을 포트폴리오 목적으로 리팩토링한 버전입니다.**  
> 원본 기능은 유지하면서 **구조, 안정성, 확장성**을 개선했습니다.

---

## ✨ 프로젝트 소개

YOLO 기반으로 실시간 영상 스트리밍을 분석하여  
**사람 탐지, 밀집도 분석, 혼잡 경고, 익명화(모자이크)** 를 수행하는 영상 관제 시스템입니다.

YouTube 실시간 스트림 또는 영상 파일을 입력으로 받아  
ROI 영역 기준으로 인원을 집계하고, 혼잡 상황을 감지하여 이벤트를 기록합니다.

---

## 🔥 프로젝트 배경 및 리팩토링

### ✔ Original Team Project

- Flask 기반 단일 구조
- FFmpeg에 YouTube URL 직접 전달 (403 오류 발생)
- 이미지 1장 기반 이벤트 저장
- 설정 및 경로 하드코딩
- 프로젝트 구조 혼재

### ✔ Refactored Portfolio Version

- Flask → **FastAPI 기반 구조 개선**
- polling → **WebSocket 실시간 스트리밍**
- streamlink 도입 → **안정적인 YouTube 스트림 처리**
- 이벤트 저장 → **전후 2초 포함 mp4 영상**
- 설정 → **.env + JSON 외부화**
- backend / frontend 구조 분리
- GPU 자동 감지 및 로깅 추가

---

## 🔑 주요 기능

- 실시간 영상 스트리밍 분석
- YOLO 기반 사람 탐지 및 추적
- ROI 기반 밀집도 분석 (히트맵)
- 혼잡 상황 감지 및 알림
- 이벤트 영상 자동 저장 (mp4 + 썸네일)
- 익명화 (모자이크 처리)
- 영상 파일 업로드 분석

---

## 🛠 기술 스택

### Backend
- FastAPI, WebSocket, Uvicorn

### Frontend
- React, react-router-dom

### AI / 분석
- Ultralytics YOLOv12
- ByteTrack

### 영상 처리
- OpenCV
- FFmpeg

### 스트리밍
- streamlink (YouTube)
- HTTP / RTSP

### Infra
- PyTorch + CUDA

---

## 🧠 핵심 처리 흐름

영상 입력 (YouTube / 파일)
   ↓
스트림 수집 (streamlink / FFmpeg)
   ↓
YOLO 객체 탐지
   ↓
객체 추적 (ByteTrack)
   ↓
ROI 기반 인원 집계
   ↓
혼잡도 판단
   ↓
이벤트 발생 시 영상 저장 (±2초)

---

## ⚙️ 실행 방법

### Backend

cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
cp config/streams.example.json config/streams.json
cp config/roi.example.json config/roi.json

uvicorn app:app --reload --port 8080

### Frontend

cd frontend
npm install
npm start

---

## 📂 프로젝트 구조

video-crowd-monitoring/
├── backend/
│   ├── app.py
│   ├── video_monitor/
│   │   ├── routes.py
│   │   ├── config.py
│   │   ├── dependencies.py
│   │   ├── schemas.py
│   │   └── services/
│   │       ├── stream_service.py
│   │       └── video_processor.py
├── frontend/
│   └── src/
├── config/
├── data/
└── README.md

---

## 📊 사용 모델

| 항목 | 내용 |
|------|------|
| 모델 | YOLOv12n |
| Precision | 0.8758 |
| Recall | 0.7911 |
| mAP50 | 0.8742 |
| mAP50-95 | 0.5809 |

---

## 🚀 핵심 포인트

- YouTube 스트리밍 문제 해결 (403 → streamlink)
- 실시간 처리 구조 개선 (polling → WebSocket)
- 단일 이미지 이벤트 → **영상 기반 이벤트 시스템**
- 설정 외부화로 운영 환경 개선
- GPU 활용 가능 구조

---

## 💡 My Role

- YOLO 기반 탐지 및 추적 파이프라인 설계
- 스트리밍 안정화 (streamlink + FFmpeg)
- 이벤트 저장 구조 설계 (순환 버퍼 기반)
- ROI 기반 밀집도 분석 로직 구현
- FastAPI 기반 백엔드 구조 리팩토링
- 포트폴리오용 코드 구조 및 실행 환경 정리

---

## 📌 한 줄 요약

실시간 영상 스트리밍을 분석하여  
👉 **밀집도 감지 및 이벤트 기록을 수행하는 AI 영상 관제 시스템을 리팩토링한 프로젝트**
