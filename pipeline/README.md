# pipeline

편집 자동화 코드를 모아두는 폴더예요.

## render.py — 편집표로 릴스 만들기

```
python3 pipeline/render.py <편집표.yaml> <원본영상폴더> <출력.mp4>
python3 pipeline/render.py <편집표.yaml> <원본영상폴더> <출력.mp4> --only 13,14   # 일부 장면만 시험
```

- 편집표 예시: `시리즈/서울생존식단/편집_v9.yaml`
- 장면마다 원본 영상 구간, 자막, 가격카드(+누적 금액), 효과(flash, glitch, shake), 영수증 정산을 적으면 자동으로 만들어요.
- 모든 클립에 천천히 줌인(켄번스), 카드가 나올 때 줌 펀치, 색 보정, 효과음(팝, 휙, 띵, 도장)을 자동으로 넣어요.
- 가로 영상은 `fit: blur`로 흐린 배경 위에 올려요.
- 62초 영상 기준 약 4분 걸려요.

## demo_motion.py

정적인 클립 하나에 움직임과 그래픽을 넣는 샘플 (디자인 기준 승인용으로 만든 것).

## fonts/

Pretendard (SIL Open Font License 1.1, https://github.com/orioncactus/pretendard)
