# pipeline

편집 자동화 코드를 모아두는 폴더예요.

- `demo_motion.py`: 정적인 클립에 움직임(천천히 줌인 + 줌 펀치)과 가격카드, 누적 금액 카운터, 상단 제목, 자막을 넣는 샘플. 디자인 기준으로 승인됨.
  ```
  python3 demo_motion.py <원본영상> <출력.mp4> <폰트폴더>
  ```
  폰트(Pretendard)는 `https://cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/public/static/Pretendard-Bold.otf`, `Pretendard-ExtraBold.otf`에서 받기.
