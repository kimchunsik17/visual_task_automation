const express = require('express');
const axios = require('axios');
const cors = require('cors');
const chalk = require('chalk');

const app = express();
const PORT = 3002; // 프론트엔드(5173), 백엔드(8000), Langfuse(3001)와 충돌하지 않는 포트
const PUBLIC_BASE_URL = (process.env.MOCK_SERVER_PUBLIC_BASE_URL || 'https://wa-pnu.duckdns.org').replace(/\/$/, '');
app.set('trust proxy', true); // nginx가 붙인 X-Forwarded-Proto를 신뢰해서 req.protocol이 https로 잡히게 함

app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

function getPublicBaseUrl(req) {
    const requestHost = req.get('host') || '';
    const isLocalRequest = /^(localhost|127\.0\.0\.1)(:\d+)?$/i.test(requestHost);

    if (!isLocalRequest) {
        return `${req.protocol}://${requestHost}`;
    }

    return PUBLIC_BASE_URL;
}

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
            <title>프리미엄 무소음 마우스 : 네이버쇼핑</title>
            <style>
                * { box-sizing: border-box; }
                body { font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', 'Segoe UI', sans-serif; background-color: #f5f6f7; color: #222; margin: 0; }

                /* ── 네이버쇼핑 스타일 상단바 ── */
                .topbar { background: #03c75a; color: #fff; padding: 10px 0; font-size: 13px; }
                .topbar-inner { max-width: 960px; margin: 0 auto; padding: 0 20px; display: flex; align-items: center; gap: 6px; }
                .topbar .logo { font-weight: 800; font-size: 18px; letter-spacing: -0.5px; }
                .topbar .logo span { font-weight: 400; opacity: .85; }
                .searchbar { flex: 1; max-width: 420px; margin-left: 24px; background: #fff; border-radius: 20px; padding: 8px 16px; color: #999; font-size: 13px; }

                .breadcrumb { max-width: 960px; margin: 14px auto 0; padding: 0 20px; font-size: 12px; color: #8a8a8a; }
                .breadcrumb b { color: #444; }

                /* ── 상품 상세 카드 ── */
                .product-wrap { max-width: 960px; margin: 16px auto 0; padding: 24px 20px; background: #fff; border-radius: 4px; display: flex; gap: 40px; }
                .gallery { width: 340px; height: 340px; flex-shrink: 0; border-radius: 8px; background: linear-gradient(135deg, #f0f2f1, #e3e6e5); display: flex; align-items: center; justify-content: center; font-size: 96px; }
                .product-info { flex: 1; padding-top: 4px; }
                .store-badge { display: inline-flex; align-items: center; gap: 4px; background: #e8f8ee; color: #03c75a; font-size: 12px; font-weight: 700; padding: 3px 8px; border-radius: 4px; }
                h1 { font-size: 22px; font-weight: 700; margin: 12px 0 8px; line-height: 1.35; }
                .rating { font-size: 13px; color: #666; margin-bottom: 18px; }
                .rating .stars { color: #03c75a; letter-spacing: -1px; }
                .price-block { border-top: 1px solid #eee; padding: 18px 0; }
                .discount-badge { color: #e33; font-size: 24px; font-weight: 800; margin-right: 8px; }
                .price { font-size: 26px; font-weight: 800; color: #222; }
                .price-original { font-size: 14px; color: #aaa; text-decoration: line-through; margin-left: 8px; }
                .delivery-row { font-size: 13px; color: #555; margin: 14px 0; display: flex; gap: 14px; }
                .delivery-row b { color: #222; }
                .qty-row { display: flex; align-items: center; gap: 10px; margin: 16px 0; font-size: 13px; color: #555; }
                .stepper { display: inline-flex; align-items: center; border: 1px solid #ddd; border-radius: 4px; overflow: hidden; }
                .stepper span { width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; }
                .stepper .qty-num { border-left: 1px solid #ddd; border-right: 1px solid #ddd; }
                .action-row { display: flex; gap: 8px; margin-top: 20px; }
                .btn-cart { flex: 1; padding: 14px; border: 1px solid #03c75a; color: #03c75a; background: #fff; border-radius: 6px; font-size: 15px; font-weight: 700; cursor: default; }
                .btn-buy { flex: 1.6; padding: 14px; border: none; background: #03c75a; color: #fff; border-radius: 6px; font-size: 15px; font-weight: 700; cursor: default; }

                /* ── 해커톤 시연 컨트롤 패널(실제 기능) ── */
                .admin-wrap { max-width: 960px; margin: 20px auto 60px; padding: 0 20px; }
                .admin-panel { background: #fff; border: 1px dashed #03c75a; border-radius: 8px; padding: 22px 24px; }
                .admin-panel .admin-title { display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 700; color: #222; margin-bottom: 4px; }
                .admin-panel .admin-tag { font-size: 11px; font-weight: 700; color: #03c75a; background: #e8f8ee; padding: 2px 7px; border-radius: 10px; }
                .admin-panel .admin-desc { font-size: 12px; color: #999; margin-bottom: 16px; }
                .input-group { margin-bottom: 14px; text-align: left; }
                label { display: block; font-size: 12px; font-weight: 700; color: #666; margin-bottom: 6px; }
                input { width: 100%; padding: 12px 14px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; background: #fafafa; transition: border-color 0.2s; }
                input:focus { border-color: #03c75a; outline: none; background: #fff; }
                #triggerBtn { background-color: #03c75a; color: white; border: none; padding: 14px 20px; font-size: 15px; font-weight: 700; border-radius: 6px; cursor: pointer; transition: background 0.2s; width: 100%; }
                #triggerBtn:hover { background-color: #02a84b; }
                #status { margin-top: 14px; font-size: 13px; font-weight: 700; min-height: 18px; }
                .success { color: #03c75a; }
                .error { color: #e74c3c; }
                .loading { color: #f39c12; }

                @media (max-width: 720px) {
                    .product-wrap { flex-direction: column; }
                    .gallery { width: 100%; }
                    .searchbar { display: none; }
                }
            </style>
        </head>
        <body>
            <div class="topbar">
                <div class="topbar-inner">
                    <div class="logo">NAVER<span> 쇼핑 (Mock)</span></div>
                    <div class="searchbar">마우스 검색...</div>
                </div>
            </div>

            <div class="breadcrumb">전자기기 &gt; PC주변기기 &gt; <b>마우스</b></div>

            <div class="product-wrap">
                <div class="gallery">🖱️</div>
                <div class="product-info">
                    <span class="store-badge">✓ 스마트스토어</span>
                    <h1>프리미엄 무소음 마우스</h1>
                    <div class="rating"><span class="stars">★★★★★</span> 4.8 · 리뷰 1,204 · 찜 320</div>

                    <div class="price-block">
                        <div><span class="discount-badge">17%</span><span class="price">35,000원</span><span class="price-original">42,000원</span></div>
                        <div class="delivery-row">
                            <span>🚚 <b>무료배송</b></span>
                            <span>오늘 출발 시 내일 도착</span>
                        </div>
                    </div>

                    <div class="qty-row">
                        수량
                        <span class="stepper"><span>−</span><span class="qty-num">1</span><span>+</span></span>
                    </div>

                    <div class="action-row">
                        <button class="btn-cart" title="시연용 목업 버튼입니다">장바구니</button>
                        <button class="btn-buy" title="시연용 목업 버튼입니다">바로구매</button>
                    </div>
                </div>
            </div>

            <div class="admin-wrap">
                <div class="admin-panel">
                    <div class="admin-title">🎬 해커톤 시연 컨트롤 <span class="admin-tag">ADMIN</span></div>
                    <div class="admin-desc">위 상품 페이지에서 실제로 "바로구매"가 눌린 것처럼, 아래 버튼이 진짜 주문 웹훅을 타겟 URL로 발송합니다.</div>

                    <div class="input-group">
                        <label for="webhookUrl">타겟 웹훅 URL</label>
                        <input type="text" id="webhookUrl" placeholder="예: http://localhost:8000/webhook/1234">
                    </div>

                    <button id="triggerBtn">🛍️ 스마트스토어 가짜 주문 발생시키기</button>
                    <div id="status"></div>
                </div>
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

// ==========================================
// 4. 결제 링크 생성 및 가상 결제창 (Payment Mock)
// ==========================================
const mockOrders = {};

app.post('/mock/payment/create-link', (req, res) => {
    const { provider, orderData } = req.body;
    
    if (!provider || !orderData) {
        return res.status(400).json({ error: "provider and orderData are required" });
    }

    const orderId = "ORD-" + Date.now() + "-" + Math.floor(Math.random() * 1000);
    mockOrders[orderId] = { provider, orderData };

    const checkoutUrl = `${getPublicBaseUrl(req)}/mock/payment/checkout/${orderId}`;
    
    console.log(chalk.magenta.bold(`\n💳 [Payment Link Created] `) + chalk.white(`Provider: ${provider}, OrderID: ${orderId}`));
    res.json({ checkoutUrl, orderId });
});

app.get('/mock/payment/checkout/:orderId', (req, res) => {
    const { orderId } = req.params;
    const order = mockOrders[orderId];

    if (!order) {
        return res.status(404).send("<h1>결제 정보를 찾을 수 없습니다.</h1><p>잘못되거나 만료된 결제 링크입니다.</p>");
    }

    let itemsHtml = "";
    let totalAmount = 0;
    
    try {
        const data = typeof order.orderData === 'string' ? JSON.parse(order.orderData) : order.orderData;
        if (data.items && Array.isArray(data.items)) {
            itemsHtml = data.items.map(item => `<li>${item.name} x ${item.qty} (₩${parseInt(item.price).toLocaleString()})</li>`).join('');
            totalAmount = data.items.reduce((sum, item) => sum + (parseInt(item.price) * parseInt(item.qty)), 0);
        } else if (data.amount) {
            itemsHtml = `<li>${data.orderName || '주문 상품'} (₩${parseInt(data.amount).toLocaleString()})</li>`;
            totalAmount = parseInt(data.amount);
        } else {
            itemsHtml = `<li>주문 정보: ${JSON.stringify(data)}</li>`;
            totalAmount = "별도 확인";
        }
    } catch (e) {
        itemsHtml = `<li>요청 데이터 파싱 실패 또는 텍스트 데이터: ${order.orderData}</li>`;
        totalAmount = "확인 불가";
    }

    const providerName = order.provider.toLowerCase() === 'naver' ? '네이버페이' : '토스페이먼츠';
    const bgColor = order.provider.toLowerCase() === 'naver' ? '#03c75a' : '#3182f6';

    res.send(`
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>\${providerName} 안전 결제</title>
            <style>
                body { font-family: 'Segoe UI', sans-serif; background-color: #f2f4f6; color: #333; margin: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
                .checkout-card { background: white; width: 100%; max-width: 400px; border-radius: 16px; box-shadow: 0 10px 20px rgba(0,0,0,0.05); overflow: hidden; }
                .header { background: \${bgColor}; color: white; padding: 20px; text-align: center; font-size: 20px; font-weight: bold; }
                .content { padding: 25px; }
                .section-title { font-size: 14px; font-weight: bold; color: #8b95a1; margin-bottom: 10px; margin-top: 20px; text-transform: uppercase; }
                .section-title:first-child { margin-top: 0; }
                ul { list-style: none; padding: 0; margin: 0 0 15px 0; border-bottom: 1px solid #f2f4f6; padding-bottom: 15px; }
                li { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 15px; }
                .total { display: flex; justify-content: space-between; font-size: 18px; font-weight: bold; color: \${bgColor}; margin-top: 15px; }
                .customer-info { background: #f9fafb; padding: 15px; border-radius: 8px; font-size: 14px; margin-bottom: 20px; }
                .customer-info p { margin: 5px 0; color: #4e5968; }
                .customer-info strong { color: #333; }
                button { width: 100%; background: \${bgColor}; color: white; border: none; padding: 16px; font-size: 16px; font-weight: bold; border-radius: 12px; cursor: pointer; transition: opacity 0.2s; }
                button:hover { opacity: 0.9; }
                .secure-badge { text-align: center; font-size: 12px; color: #b0b8c1; margin-top: 15px; display: flex; align-items: center; justify-content: center; gap: 5px; }
            </style>
        </head>
        <body>
            <div class="checkout-card">
                <div class="header">
                    \${providerName} 결제
                </div>
                <div class="content">
                    <div class="section-title">주문 상품 정보</div>
                    <ul>
                        \${itemsHtml}
                    </ul>
                    <div class="total">
                        <span>총 결제금액</span>
                        <span>₩\${typeof totalAmount === 'number' ? totalAmount.toLocaleString() : totalAmount}</span>
                    </div>

                    <div class="section-title">주문자 정보 (자동 연동)</div>
                    <div class="customer-info">
                        <p><strong>배송지:</strong> 등록된 기본 배송지 (서울시 강남구 테헤란로 123)</p>
                        <p><strong>연락처:</strong> 010-****-1234</p>
                        <p><strong>이메일:</strong> user@example.com</p>
                        <p style="font-size: 12px; color: #8b95a1; margin-top: 10px;">* \${providerName}에 등록된 안심 회원 정보로 안전하게 결제됩니다.</p>
                    </div>

                    <button onclick="alert('결제가 성공적으로 완료되었습니다! (시뮬레이션)')">₩\${typeof totalAmount === 'number' ? totalAmount.toLocaleString() : totalAmount} 결제하기</button>
                    <div class="secure-badge">
                        🔒 안전한 256-bit 암호화 결제
                    </div>
                </div>
            </div>
        </body>
        </html>
    `);
});

app.listen(PORT, () => {
    console.log(chalk.cyan.bold(`\n======================================================`));
    console.log(chalk.cyan.bold(` 🚀 MVP Demo Mock API Server running on port ${PORT}`));
    console.log(chalk.white(`    👉 대시보드 URL: http://localhost:${PORT}`));
    console.log(chalk.white(`    👉 외부 접근 기본 URL: ${PUBLIC_BASE_URL}`));
    console.log(chalk.cyan.bold(`======================================================\n`));
});
