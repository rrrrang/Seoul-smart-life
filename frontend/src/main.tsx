/*
 * React 앱 진입점: HTML의 root에 App 컴포넌트를 마운트합니다.
 * 안내: 실행 로직은 변경하지 않고 설명 주석만 추가한 버전입니다.
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'


// [렌더링] React StrictMode를 적용해 App을 화면에 렌더링합니다.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
