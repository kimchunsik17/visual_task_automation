const express = require('express');
const axios = require('axios');
const cors = require('cors');
const chalk = require('chalk');

const app = express();
const PORT = 3001; // 프론트엔드(5173), 백엔드(8000)와 충돌하지 않는 포트

app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// ==========================================
// 3. 심사위원 시연용 미니 대시보드 (Admin UI)
// ==========================================
app.get('/', (req, res) => {
    res.send(`
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Mock API Dashboard</title>
            <style>
                body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; color: #333; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
                .card { background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); width: 450px; text-align: center; }
                h1 { font-size: 22px; color: #2c3e50; margin-bottom: 25px; }
                .input-group { margin-bottom: 20px; text-align: left; }
                label { display: block; font-size: 13px; font-weight: bold; color: #555; margin-bottom: 5px; }
                input { width: 90%; padding: 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; background: #fdfdfd; transition: border-color 0.2s; }
                input:focus { border-color: #03c75a; outline: none; }
                button { background-color: #03c75a; color: white; border: none; padding: 14px 20px; font-size: 16px; font-weight: bold; border-radius: 8px; cursor: pointer; transition: background 0.3s; width: 100%; }
                button:hover { background-color: #02a84b; }
                #status { margin-top: 20px; font-size: 14px; font-weight: bold; min-height: 20px; }
                .success { color: #03c75a; }
                .error { color: #e74c3c; }
                .loading { color: #f39c12; }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>🛍️ 스마트스토어 주문 시뮬레이터</h1>
                
                <div class="input-group">
                    <label for="webhookUrl">타겟 웹훅 URL (해커톤 시연용)</label>
                    <input type="text" id="webhookUrl" placeholder="예: http://localhost:8000/webhook/1234">
                </div>

                <button id="triggerBtn">[스마트스토어 가짜 주문 발생시키기]</button>
                <div id="status"></div>
            </div>

            <script>
                document.getElementById('triggerBtn').addEventListener('click', async () => {
                    const webhookUrl = document.getElementById('webhookUrl').value.trim();
                    const statusEl = document.getElementById('status');
                    
                    if (!webhookUrl) {
                        statusEl.textContent = '❌ 웹훅 URL을 입력해주세요.';
                        statusEl.className = 'error';
                        return;
                    }

                    statusEl.textContent = '주문 전송 준비 중... ⏳';
                    statusEl.className = 'loading';

                    try {
                        const response = await fetch('/mock/naver/trigger-order', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ targetWebhookUrl: webhookUrl })
                        });
                        
                        const result = await response.json();
                        if (response.ok) {
                            statusEl.textContent = '✅ 성공: ' + result.message + ' (지연: ' + result.delay + 'ms)';
                            statusEl.className = 'success';
                        } else {
                            statusEl.textContent = '❌ 실패: ' + (result.error || '알 수 없는 오류');
                            statusEl.className = 'error';
                        }
                    } catch (error) {
                        statusEl.textContent = '❌ 서버와 통신할 수 없습니다: ' + error.message;
                        statusEl.className = 'error';
                    }
                });
            </script>
        </body>
        </html>
    `);
});

// ==========================================
// 1. 네이버 스마트스토어 주문 발생 트리거기
// ==========================================
app.post('/mock/naver/trigger-order', (req, res) => {
    const { targetWebhookUrl } = req.body;

    if (!targetWebhookUrl) {
        return res.status(400).json({ error: 'targetWebhookUrl is required' });
    }

    console.log(chalk.blue.bold(`\n[Naver Trigger] 📦 새로운 주문 생성 요청 수신. 타겟 URL: ${targetWebhookUrl}`));

    // 네이버 커머스 API ProductOrder 모델을 본딴 100% 동일한 구조의 더미 데이터
    const dummyOrder = {
        ProductOrder: {
            ProductOrderId: "20260715" + Math.floor(Math.random() * 1000000),
            OrderNo: "20260715" + Math.floor(Math.random() * 1000000),
            ProductName: "프리미엄 무소음 마우스",
            TotalPaymentAmount: 35000,
            OrderStatus: "PAYED",
            PaymentDate: new Date().toISOString(),
            ShippingAddress: {
                ZipCode: "12345",
                BaseAddress: "서울특별시 강남구 테헤란로 123",
                DetailedAddress: "10층 1004호"
            },
            BuyerId: "demo_user_01",
            BuyerName: "해커톤심사위원"
        }
    };

    // 현실감을 높이기 위한 500ms ~ 1500ms 무작위 지연 (Latency)
    const latency = Math.floor(Math.random() * 1000) + 500;
    console.log(chalk.yellow(`[Naver Trigger] ⏳ 현실감을 위해 ${latency}ms 지연 후 웹훅 발송을 시작합니다...`));

    setTimeout(async () => {
        try {
            const response = await axios.post(targetWebhookUrl, dummyOrder);
            console.log(chalk.green.bold(`[Naver Trigger] ✅ 웹훅 발송 성공! (상태 코드: ${response.status})`));
        } catch (error) {
            console.log(chalk.red.bold(`[Naver Trigger] ❌ 웹훅 발송 실패! (오류: ${error.message})`));
        }
    }, latency);

    // 대시보드 화면에는 요청 접수 완료를 바로 리턴
    res.json({ message: '주문이 생성되고 웹훅 전송이 스케줄링되었습니다.', delay: latency });
});


// ==========================================
// 2. 카카오 알림톡 수신 서버 (Mock Action Server)
// ==========================================
app.post('/mock/kakao/alimtalk', (req, res) => {
    const { templateCode, receiverPhone, message } = req.body;

    // 2-1. 필수 파라미터 검증 로직
    if (!templateCode || !receiverPhone || !message) {
        console.log(chalk.bgRed.white.bold(`\n [카카오 알림톡 발송 실패] `) + chalk.red(` 필수 파라미터 누락`));
        return res.status(400).json({ 
            error: "Bad Request", 
            message: "templateCode, receiverPhone, message are required parameters." 
        });
    }

    // 2-2. 정상 수신 시 터미널 콘솔에 직관적으로 출력 (색상 적용)
    console.log(chalk.bgGreen.black.bold(`\n 🟩 [카카오톡 발송 성공] `));
    console.log(chalk.green(` ├── 수신자: ${receiverPhone}`));
    console.log(chalk.green(` ├── 템플릿: ${templateCode}`));
    console.log(chalk.green(` └── 내용: ${message.replace(/\n/g, '\\n')}`));

    // 알림톡 대행사 스펙처럼 200 OK와 리절트 반환
    res.status(200).json({ 
        result: "SUCCESS", 
        message: "알림톡이 성공적으로 발송 처리되었습니다." 
    });
});

app.listen(PORT, () => {
    console.log(chalk.cyan.bold(`\n======================================================`));
    console.log(chalk.cyan.bold(` 🚀 MVP Demo Mock API Server running on port ${PORT}`));
    console.log(chalk.white(`    👉 대시보드 URL: http://localhost:${PORT}`));
    console.log(chalk.cyan.bold(`======================================================\n`));
});
