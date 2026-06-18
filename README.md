# Merchant Campaign Email Agent

Tự động sinh email đề xuất hợp tác chương trình khuyến mãi (CTKM) từ Zalopay gửi đến merchant, dựa trên dữ liệu campaign và các mẫu email đã được duyệt trước đó.

Được xây dựng cho **GreenNode Claw-a-thon 2026** và triển khai trên **GreenNode AgentBase**.

---

## Tính năng

- **Sinh email tự động** từ dữ liệu campaign (merchant, tên CTKM, timeline, ưu đãi, kênh, CTA)
- **Self-review & auto-fix**: Agent tự chấm điểm email (1–5) và tự sửa nếu chưa đạt ngưỡng (≥ 4/5)
- **RAG-lite**: Dùng các email đã approve trước đó làm style reference cho lần sinh tiếp theo
- **Merchant mới**: Hỗ trợ nhập thông tin campaign thủ công nếu merchant chưa có trong file dữ liệu; tự động dùng email mẫu của merchant khác làm tham khảo
- **Chế độ nhanh**: Bỏ qua review để giảm ~50% thời gian phản hồi
- **Web UI tích hợp**: Giao diện HTML/JS phục vụ ngay tại `GET /`, không cần deploy frontend riêng
- **Edit & Approve**: Chỉnh sửa email trực tiếp trên UI trước khi approve; email approved được lưu làm mẫu cho lần sau

---

## Kiến trúc

```
POST /invocations          ← AgentBase entrypoint (main.py)
GET  /                     ← Web UI (HTML/JS, không cần frontend riêng)
POST /approve              ← Lưu email đã duyệt vào approved_emails/
GET  /merchants            ← Danh sách merchant để autocomplete
GET  /health               ← Health check (AgentBase runtime)
```

```
main.py                    ← AgentBase entrypoint + Web UI + API routes
src/
  agent.py                 ← Orchestrator: điều phối toàn bộ pipeline
  data_reader.py           ← Đọc campaign.xlsx, tra cứu merchant
  email_generator.py       ← Sinh email qua LLM
  self_reviewer.py         ← Review + auto-fix qua LLM
data/
  campaign.xlsx            ← Dữ liệu campaign (Merchant, Campaign Name, Timeline, ...)
prompts/
  email_generation.txt     ← Prompt template sinh email
  self_review.txt          ← Prompt template review email
approved_emails/           ← Email đã approve — dùng làm style reference
```

### Pipeline mỗi request

```
1. Tra cứu merchant trong campaign.xlsx
   └─ Không tìm thấy + có campaign_info → dùng dữ liệu thủ công
2. Load approved email samples (merchant cụ thể → cross-merchant fallback)
3. Sinh email (LLM call #1)
4. [skip_review=false] Review email (LLM call #2)
   └─ Score < 4/5 → Auto-fix + review lại (tối đa 1 lần)
5. Trả kết quả: subject, body, score, generation_history
```

---

## Cài đặt & chạy local

### Yêu cầu

- Python 3.10+
- Docker Desktop (để build và deploy)
- GreenNode IAM credentials (để deploy lên AgentBase)

### Cài đặt

```bash
git clone <repo-url>
cd merchant-campaign-email-agent

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux

pip install -r requirements.txt
```

### Cấu hình

```bash
copy .env.example .env   # Windows
# cp .env.example .env   # Mac/Linux
```

Chỉnh sửa `.env`:

```env
# GreenNode MaaS (khuyến nghị)
LLM_API_KEY=<maas-api-key>
LLM_BASE_URL=https://maas-llm-aiplatform-hcm.api.vngcloud.vn
LLM_MODEL=minimax/minimax-m2.5   # hoặc qwen/qwen3-5-27b, google/gemma-4-31b-it

# Fallback: Anthropic API (local dev)
# ANTHROPIC_API_KEY=<anthropic-api-key>
```

### Chạy server

```bash
python main.py
# Mở http://localhost:8080 để dùng Web UI
```

### Chạy tests

```bash
pytest tests/
```

---

## Deploy lên AgentBase

### Yêu cầu thêm

- Docker Desktop đang chạy
- GreenNode IAM credentials (`GREENNODE_CLIENT_ID`, `GREENNODE_CLIENT_SECRET`)

### Các bước

```bash
# 1. Build image (linux/amd64 bắt buộc)
docker build --platform linux/amd64 -t vcr.vngcloud.vn/<repo>/email-ctkm-agent:latest .

# 2. Login AgentBase Container Registry
bash .claude/skills/agentbase/scripts/cr.sh credentials docker-login

# 3. Push image
docker push vcr.vngcloud.vn/<repo>/email-ctkm-agent:latest

# 4. Tạo hoặc update runtime
bash .claude/skills/agentbase/scripts/runtime.sh create \
  --name "email-ctkm-agent" \
  --image "vcr.vngcloud.vn/<repo>/email-ctkm-agent:latest" \
  --flavor "runtime-s2-general-2x4" \
  --env-file .env \
  --from-cr
```

Hoặc dùng `/agentbase-deploy` skill trong Claude Code để thực hiện tự động.

**Console:** https://aiplatform.console.vngcloud.vn/agent-runtime?tab=runtime

---

## API

### `POST /invocations`

Sinh email cho một merchant.

**Request body:**

```json
{
  "merchant_name": "KFC",
  "user_instruction": "Viết ngắn gọn, không quá 150 từ",
  "skip_review": false,
  "campaign_info": {
    "Campaign Name": "Summer Sale 2026",
    "Timeline": "01/07 – 31/07/2026",
    "Scheme": "Giảm 20.000đ cho đơn từ 99.000đ",
    "Sponsor": "Zalopay tài trợ 100%",
    "Channel": "App Zalopay",
    "CTA": "Xác nhận trước 25/06/2026"
  }
}
```

| Field | Bắt buộc | Mô tả |
|---|---|---|
| `merchant_name` | ✓ | Tên merchant (tìm trong campaign.xlsx) |
| `user_instruction` | | Yêu cầu thêm về văn phong, độ dài, ... |
| `skip_review` | | `true` = bỏ qua review, nhanh hơn ~50% |
| `campaign_info` | | Thông tin campaign thủ công (nếu merchant chưa có trong file) |

**Response:**

```json
{
  "merchant": "KFC",
  "campaign": "World Cup 2026",
  "subject": "Đề xuất triển khai CTKM World Cup 2026 cùng Zalopay",
  "body": "Kính gửi Anh/Chị, ...",
  "review": {
    "score": 5,
    "passed": true,
    "strengths": ["..."],
    "weaknesses": [],
    "improvement_suggestions": []
  },
  "attempts": 1,
  "approved_samples_used": 3,
  "approved_files": ["kfc_20260616_163519.txt", "..."],
  "generation_history": [
    { "attempt": 1, "score": 5, "reason": "Accepted (5/5)" }
  ]
}
```

### `POST /approve`

Lưu email đã duyệt làm mẫu tham khảo cho lần sau.

```json
{
  "merchant": "KFC",
  "subject": "Tiêu đề email",
  "body": "Nội dung email..."
}
```

File được lưu tại `approved_emails/{merchant}_{timestamp}.txt` và tự động được dùng trong request tiếp theo.

### `GET /merchants`

Trả về danh sách merchant trong campaign.xlsx.

```json
{ "merchants": ["KFC", "BreadTalk", "..."] }
```

### `GET /health`

Health check — trả về HTTP 200 khi agent sẵn sàng.

---

## Biến môi trường

| Biến | Bắt buộc | Mô tả |
|---|---|---|
| `LLM_API_KEY` | ✓ | GreenNode MaaS API key (Bearer token) |
| `LLM_BASE_URL` | | MaaS endpoint (default: GreenNode HCM) |
| `LLM_MODEL` | | Model ID (default: `minimax/minimax-m2.5`) |
| `ANTHROPIC_API_KEY` | | Fallback cho local dev không dùng MaaS |

Các biến sau được **AgentBase Runtime tự inject** — không đặt thủ công:
`GREENNODE_CLIENT_ID`, `GREENNODE_CLIENT_SECRET`, `GREENNODE_AGENT_IDENTITY`, `GREENNODE_ENDPOINT_URL`

---

## Approved emails & style reference

Cơ chế RAG-lite:

1. Email được approve qua UI → lưu vào `approved_emails/{merchant}_{timestamp}.txt`
2. Lần sinh tiếp theo cho cùng merchant → agent load tối đa 3 file mới nhất làm style reference
3. Merchant chưa có file riêng → dùng file của merchant khác (cross-merchant fallback)
4. File được commit vào git → bake vào Docker image → persist qua các lần redeploy

---

## Models được hỗ trợ (GreenNode MaaS)

| Model | Model ID |
|---|---|
| Minimax M2.5 (default) | `minimax/minimax-m2.5` |
| Qwen3 | `qwen/qwen3-5-27b` |
| Gemma 4 | `google/gemma-4-31b-it` |

Xem danh sách đầy đủ: `GET https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1/models`
