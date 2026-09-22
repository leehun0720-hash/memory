# 대화 아바타·음성 개선 조사

조사일: 2026-09-21. 범위: 로컬 구현/비밀이 아닌 설정 점검 및 공급자 공식 문서 조사. 실제 음성 청취, 유료 생성, 지연 실측, 공급자 전환은 하지 않았다. 아래 우선순위는 검증할 가설이며 품질 보장이 아니다.

## 결론

기존 ElevenLabs 음성을 원본 자료와 한국어 문장 단위로 먼저 비교·조정하고, 실패 시 음성이 바뀌는 경로와 중복 합성을 고친다. 이어 동일 음성으로 현재 D-ID와 Simli 실시간 전송을 비교한다. D-ID Echo는 v4 expressive 전용이므로 기존 사진 talk 아바타에 단순 적용할 수 있다고 가정하지 않는다.

## 확인한 현재 구현

- 설정: tts_provider=auto, tts_model=eleven_multilingual_v2, 별도 tts_voice_settings 없음, avatar_provider=auto. 등록된 일부 인물의 공급자는 ElevenLabs/D-ID다. 비밀 키는 이 문서에 기록하지 않는다.
- `server/ai/tts.py`: 기본 stability=0.4, similarity_boost=0.8, style=0.35, speed=0.95. 완성된 MP3 44.1kHz/64kbps를 반환한다. 모델 선택 목록에는 v3, v3 conversational, flash v2.5도 이미 있다. 목록 존재만으로 계정/API 호환 검증이 끝난 것은 아니다.
- `server/face.py:speech_url`: 전체 음성을 합성한 뒤 D-ID에 업로드하여 URL을 반환한다.
- `server/ai/avatar.py`: D-ID 사진 기반 talk agent와 SDK 2.0.10 사용. agent의 Microsoft 음성 지정은 외부 ElevenLabs 오디오 재생 시 실제 합성 모델을 뜻하지 않는다.
- `server/static/js/app.js:speakAs`: D-ID 실패 뒤 /tts에서 재합성할 수 있다. 이어 ready 아바타에 Blob을 보내는 일반 경로는 문자열을 기대하는 DIDAvatar에도 도달할 수 있다. 최종적으로 브라우저 기본 음성으로 내려간다. 이 경로가 이번 불만 당시 실행됐는지는 확인하지 않았다.
- D-ID 정상 경로의 소리는 아바타 영상 스트림에 포함된다. 현재 소리와 영상을 항상 따로 재생한다고 진단하면 안 된다.
- Simli 경로도 완성 MP3를 브라우저에서 PCM으로 변환하고 한번에 청크 전송한다. 단순 공급자 설정 전환만으로 종단 간 스트리밍이 완성되지 않는다.

## 권장 실행 순서

1. 원본 음성에서 한 사람의 깨끗하고 일관된 말투 1~2분을 선별한다. 과도한 잡음 제거로 음색을 손상하지 않도록 원본과 비교한다. 사진은 정면 얼굴과 입이 선명한 원본을 사용하고 액자·반사·가림을 줄인다. 자료를 외부에 새로 올리는 것은 별도 구현/검증 단계다.
2. 동일한 한국어 20문장으로 Multilingual v2, Flash v2.5, v3 Conversational을 비교한다. 평상 대화는 짧은 1~2문장으로 만든다. 이름·날짜·숫자 발음을 정리한다. 차분한 음성을 위한 초기 실험값은 v2 stability 0.5, style 0~0.15, speed 0.95~1.0, similarity_boost 0.8이며 최적값으로 단정하지 않는다. 모델별 지원 파라미터는 API 확인이 필요하다.
3. 아바타 실패 시 이미 생성한 음성을 재사용하여 사진+동일 목소리로 재생한다. 음성 자체가 실패하면 재시도/자막을 제공하고 일반 목소리 사용은 명시적으로 구분한다. 중복 합성, DID에 Blob 전달, UI의 너무 이른 speaking 상태를 수정한다.
4. 문장 경계를 지키는 TTS 스트리밍 → 아바타 오디오 스트리밍 → WebRTC 재생으로 개선한다. 아주 짧은 텍스트 조각마다 합성하면 운율이 깨질 수 있으므로 문장 단위 큐, 중단/취소, 오디오 순서 보존을 함께 구현한다.
5. 기존 D-ID와 Simli를 같은 사진·음성으로 비교한다. Simli는 기존 어댑터가 있어 비교 구현 부담이 상대적으로 작지만 신규 SDK/세션 호환성 확인이 필요하다. D-ID Echo는 v4 아바타 생성 조건과 현재 인물 자료의 적용 가능성을 먼저 확인한다. 기존 face_id를 삭제/교체하지 말고 시험용 등록을 분리한다.

## 품질·비용 판단

- Flash v2.5는 공식 문서상 약 75ms 모델 지연과 낮은 문자 단가를 강조한다. v3 Conversational은 약 280ms와 표현력에 초점을 둔다. 이는 전체 대화 응답 시간이나 한국어 복제 품질의 실측값이 아니다.
- 음질 비교는 모델 이름을 숨기고 가족이 유사도·자연스러움·편안함을 각각 평가한다. 한국어에서 어느 모델이 가장 좋은지는 실제 등록 음성으로 결정한다.
- 입모양은 ㅁ/ㅂ/ㅍ 문장, 얼굴 윤곽·치아 왜곡, 말이 끝난 뒤 잔여 움직임을 평가한다. 목표 예시: 입과 소리 차이 150ms 이내, 첫 소리 중앙값 2초 이내. 모두 제안 목표이며 달성 결과가 아니다.
- 10분 대화당 실제 TTS 문자 비용 + 아바타 세션/생성 과금 + 재시도 비용을 기록한다. 기다리는 시간의 과금 여부와 계정 할인까지 확인해야 공급자 비용 비교가 가능하다. 공개 지연 수치만으로 총비용 절감률을 약속하지 않는다.
- 전체 교체 전 동일 음성의 아바타 비교와 음성 단독 청취를 분리하면 원인을 구분할 수 있다. 64kbps MP3 개선도 비교 항목이지만 원본 녹음이나 음성 모델의 문제를 비트레이트만으로 해결할 수는 없다.

## 공식 자료

- ElevenLabs 모델: https://elevenlabs.io/docs/overview/models
- 모델 선택: https://elevenlabs.io/docs/eleven-api/choosing-the-right-model
- 복제 원본 품질: https://help.elevenlabs.io/hc/en-us/articles/13416206830097-Are-there-any-tips-to-get-good-quality-cloned-voices
- D-ID 외부 오디오 Echo(v4 전용): https://docs.d-id.com/docs/echo-sessions-quickstart
- Simli 실시간 립싱크/LiveKit: https://docs.simli.com/overview

다음 에이전트: 연구 단계다. 코드·저장된 공급자 설정은 변경하지 않았다. 유료 테스트 결과나 품질 개선 완료로 보고하지 말 것.
