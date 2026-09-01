---
okf_version: "0.2"
---

# LLM-Wiki — bundle index

TL;DR: Knowledge bundle theo OKF v0.2, do LLM duy trì, con người lái hướng. Bắt đầu ở đây, đi theo tập link nhỏ nhất — không nạp cả bundle.

## Bắt đầu
- [[overview|Overview]] — vision, ràng buộc, các quyết định thiết kế
- [[SCHEMA|SCHEMA]] — hợp đồng format & quy ước (đọc trước mọi thao tác)

## Kiến thức — profile: codebase
- [[requirements/index|Requirements]] — ý định sản phẩm, ràng buộc, open questions
- [[decisions/index|Decisions (ADR)]] — quyết định & đánh đổi
- [[modules/index|Modules]] — kiến trúc & hành vi quan sát của code
- [[guides/index|Guides]] — how-to, onboarding
- [[alerts/index|Alerts]] — mâu thuẫn, open questions, gaps

## Vận hành (không phải concept)
- `log.md` — lịch sử thay đổi theo thời gian
- `wiki.config.toml` — cấu hình profile, retrieval, models
- `registry.yml` — reserve Concept ID, chống fork
- `pins.yml` — sửa tay của con người
- `raw/` — nguồn bất biến, chỉ đọc
- `.wiki-index/` — chỉ mục search derived (gitignored, rebuild được)

> Điều hướng: mỗi mục trỏ tới section index; drill vào từng concept. Concept ID = đường dẫn file bỏ `.md`.
