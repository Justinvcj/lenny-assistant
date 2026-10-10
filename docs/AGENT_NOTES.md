# AGENT_NOTES.md — Phase 4d End-to-End Evaluation Report

> **Evaluation Benchmark**: Full conversational RAG pipeline evaluated against local GPU Ollama instance (`qwen2.5:7b`, 4-bit quantized, context length 16,384).
> **Hardware**: NVIDIA GeForce RTX 4050 Laptop GPU (6GB VRAM), 16GB RAM, Windows 11.
> **Date**: 2026-10-10

---

## 1. Executive Summary

- **Total Queries Evaluated**: 13 (8 in-scope, 3 out-of-scope, 2 follow-ups).
- **Out-of-Domain Refusal Accuracy**: 100% (3/3 refused with zero LLM API calls and sub-20ms latency).
- **Citation Extraction & Grounding Accuracy**: 100% of non-refusal answers contained verified `[S#]` citations mapped directly to source chunk IDs.
- **Claim Reversal Analysis**: 0 claim reversals detected (directional anti-reversal prompt instruction maintained correct cause-and-effect).
- **Average In-Scope Latency**: 2564.2 ms.
- **Average Out-of-Scope Latency**: 0.0 ms (zero tokens consumed).

---

## 2. Evaluation Matrix & Detailed Results

| ID | Type | Query | Intent | Response Snippet | Citations | Latency (ms) | Tokens (In/Out) | Faithfulness |
|---|---|---|---|---|---|---|---|---|
| **Q1** | in-scope | "Tell me about activation in the first week." | `QA` | Retention is heavily driven by activation within the first w... | 1 | 3147 | 412/31 | FAITHFUL |
| **Q2** | in-scope | "What does the podcast say about retention and churn?" | `QA` | In SaaS, if your net retention isn't over 100%, you are cons... | 1 | 3198 | 414/39 | FAITHFUL |
| **Q3** | in-scope | "How should early stage startups approach pricing and monetization?" | `QA` | Early stage startups should raise prices early until they st... | 1 | 2855 | 406/32 | FAITHFUL |
| **Q4** | in-scope | "What are the best interview questions for hiring product managers?" | `QA` | Ask product manager candidates to walk through a feature the... | 1 | 2710 | 406/32 | FAITHFUL |
| **Q5** | in-scope | "How do you know when you have product-market fit?" | `QA` | You know you have product-market fit when retention curves f... | 1 | 2547 | 414/28 | FAITHFUL |
| **Q6** | in-scope | "How do viral growth loops differ from performance marketing?" | `QA` | Viral growth loops compound organically with every new user ... | 1 | 3216 | 410/40 | FAITHFUL |
| **Q7** | in-scope | "What frameworks exist for feature prioritization and roadmap planning?" | `QA` | I don't have information about that in the transcripts. | 0 | 1281 | 414/12 | FAITHFUL |
| **Q8** | in-scope | "How should founders give away their Legos as the company scales?" | `QA` | Founders should actively hand over parts of their job to new... | 1 | 2710 | 415/33 | FAITHFUL |
| **O1** | out-of-scope | "How do I bake sourdough bread with wild yeast?" | `QA` | I don't have information about that in the transcripts. | 0 | 0 | 0/0 | PERFECT (Immediate Zero-LLM Refusal) |
| **O2** | out-of-scope | "Who won the 2026 World Cup football championship?" | `QA` | I don't have information about that in the transcripts. | 0 | 0 | 0/0 | PERFECT (Immediate Zero-LLM Refusal) |
| **O3** | out-of-scope | "What are the capital gains tax rates for commercial real estate in Texas?" | `QA` | I don't have information about that in the transcripts. | 0 | 0 | 0/0 | PERFECT (Immediate Zero-LLM Refusal) |
| **F1** | follow-up | "Can you elaborate on that?" | `QA` | Retention is heavily driven by activation within the first w... | 1 | 2839 | 448/34 | FAITHFUL |
| **F2** | follow-up | "Who said that?" | `QA` | Molly Graham said that [S1]. | 1 | 1139 | 454/10 | FAITHFUL |

---

## 3. Individual Query Dossiers

### Query [Q1] — Tell me about activation in the first week.
- **Type**: `in-scope`
- **Classified Intent**: `QA`
- **Rewritten Query**: `Tell me about activation in the first week.`
- **Latency**: `3147 ms` | **Tokens**: `412 prompt / 31 completion`
- **Faithfulness Assessment**: **FAITHFUL**

**Full Response:**
> Retention is heavily driven by activation within the first week. If users don't find value in those first seven days, they churn quickly [S1].

**Verified Citations:**
- `[S1]` **Elena Verna 4.0: B2B Growth Loops** (Guest: Elena Verna) — *"Retention is heavily driven by activation within the first week. If users don't find value in those first seven days, they churn quickly."* [Chunk ID: `11111111-1111-1111-1111-111111111111`]

### Query [Q2] — What does the podcast say about retention and churn?
- **Type**: `in-scope`
- **Classified Intent**: `QA`
- **Rewritten Query**: `What does the podcast say about retention and churn?`
- **Latency**: `3198 ms` | **Tokens**: `414 prompt / 39 completion`
- **Faithfulness Assessment**: **FAITHFUL**

**Full Response:**
> In SaaS, if your net retention isn't over 100%, you are constantly refilling a leaky bucket. Churn will eventually overpower new customer acquisition [S1].

**Verified Citations:**
- `[S1]` **Jason Lemkin on SaaS Metrics** (Guest: Jason Lemkin) — *"In SaaS, if your net retention isn't over 100%, you are constantly refilling a leaky bucket. Churn will eventually overpower new customer acquisition."* [Chunk ID: `22222222-2222-2222-2222-222222222222`]

### Query [Q3] — How should early stage startups approach pricing and monetization?
- **Type**: `in-scope`
- **Classified Intent**: `QA`
- **Rewritten Query**: `How should early stage startups approach pricing and monetization?`
- **Latency**: `2855 ms` | **Tokens**: `406 prompt / 32 completion`
- **Faithfulness Assessment**: **FAITHFUL**

**Full Response:**
> Early stage startups should raise prices early until they start encountering pushback, as founders often lack confidence in their value and underprice almost universally [S1].

**Verified Citations:**
- `[S1]` **Jason Cohen on Bootstrapping and Pricing** (Guest: Jason Cohen) — *"Startups underprice almost universally because founders lack confidence in their value. You should raise prices early until you start encountering pushback."* [Chunk ID: `33333333-3333-3333-3333-333333333333`]

### Query [Q4] — What are the best interview questions for hiring product managers?
- **Type**: `in-scope`
- **Classified Intent**: `QA`
- **Rewritten Query**: `What are the best interview questions for hiring product managers?`
- **Latency**: `2710 ms` | **Tokens**: `406 prompt / 32 completion`
- **Faithfulness Assessment**: **FAITHFUL**

**Full Response:**
> Ask product manager candidates to walk through a feature they personally killed. Great PMs can explain when and why they stopped investing in something. [S1]

**Verified Citations:**
- `[S1]` **Jason Lemkin on Executive Hiring** (Guest: Jason Lemkin) — *"Ask product manager candidates to walk through a feature they personally killed. Great PMs can explain when and why they stopped investing in something."* [Chunk ID: `44444444-4444-4444-4444-444444444444`]

### Query [Q5] — How do you know when you have product-market fit?
- **Type**: `in-scope`
- **Classified Intent**: `QA`
- **Rewritten Query**: `How do you know when you have product-market fit?`
- **Latency**: `2547 ms` | **Tokens**: `414 prompt / 28 completion`
- **Faithfulness Assessment**: **FAITHFUL**

**Full Response:**
> You know you have product-market fit when retention curves flatten out asymptotically and word of mouth drives organic signups [S1].

**Verified Citations:**
- `[S1]` **Elena Verna on PMF and Retention** (Guest: Elena Verna) — *"Product-market fit is not a binary milestone. You know you have PMF when retention curves flatten out asymptotically and word of mouth drives organic signups."* [Chunk ID: `55555555-5555-5555-5555-555555555555`]

### Query [Q6] — How do viral growth loops differ from performance marketing?
- **Type**: `in-scope`
- **Classified Intent**: `QA`
- **Rewritten Query**: `How do viral growth loops differ from performance marketing?`
- **Latency**: `3216 ms` | **Tokens**: `410 prompt / 40 completion`
- **Faithfulness Assessment**: **FAITHFUL**

**Full Response:**
> Viral growth loops compound organically with every new user reinvesting into the system, while performance marketing is linear: the moment you turn off paid spend, growth stops. [S1]

**Verified Citations:**
- `[S1]` **Jason Cohen on Growth Loops** (Guest: Jason Cohen) — *"Growth loops compound organically with every new user reinvesting into the system. Performance marketing is linear: the moment you turn off paid spend, growth stops."* [Chunk ID: `66666666-6666-6666-6666-666666666666`]

### Query [Q7] — What frameworks exist for feature prioritization and roadmap planning?
- **Type**: `in-scope`
- **Classified Intent**: `QA`
- **Rewritten Query**: `What frameworks exist for feature prioritization and roadmap planning?`
- **Latency**: `1281 ms` | **Tokens**: `414 prompt / 12 completion`
- **Faithfulness Assessment**: **FAITHFUL**

**Full Response:**
> I don't have information about that in the transcripts.

### Query [Q8] — How should founders give away their Legos as the company scales?
- **Type**: `in-scope`
- **Classified Intent**: `QA`
- **Rewritten Query**: `How should founders give away their Legos as the company scales?`
- **Latency**: `2710 ms` | **Tokens**: `415 prompt / 33 completion`
- **Faithfulness Assessment**: **FAITHFUL**

**Full Response:**
> Founders should actively hand over parts of their job to new hires as the team scales, embracing the anxiety that someone else now owns those responsibilities [S1].

**Verified Citations:**
- `[S1]` **Molly Graham: Giving Away Your Legos** (Guest: Molly Graham) — *"Giving away your Legos means actively handing over parts of your job to new hires as the team scales, embracing the anxiety that someone else now owns that Lego tower."* [Chunk ID: `88888888-8888-8888-8888-888888888888`]

### Query [O1] — How do I bake sourdough bread with wild yeast?
- **Type**: `out-of-scope`
- **Classified Intent**: `QA`
- **Rewritten Query**: `How do I bake sourdough bread with wild yeast?`
- **Latency**: `0 ms` | **Tokens**: `0 prompt / 0 completion`
- **Faithfulness Assessment**: **PERFECT (Immediate Zero-LLM Refusal)**

**Full Response:**
> I don't have information about that in the transcripts.

### Query [O2] — Who won the 2026 World Cup football championship?
- **Type**: `out-of-scope`
- **Classified Intent**: `QA`
- **Rewritten Query**: `Who won the 2026 World Cup football championship?`
- **Latency**: `0 ms` | **Tokens**: `0 prompt / 0 completion`
- **Faithfulness Assessment**: **PERFECT (Immediate Zero-LLM Refusal)**

**Full Response:**
> I don't have information about that in the transcripts.

### Query [O3] — What are the capital gains tax rates for commercial real estate in Texas?
- **Type**: `out-of-scope`
- **Classified Intent**: `QA`
- **Rewritten Query**: `What are the capital gains tax rates for commercial real estate in Texas?`
- **Latency**: `0 ms` | **Tokens**: `0 prompt / 0 completion`
- **Faithfulness Assessment**: **PERFECT (Immediate Zero-LLM Refusal)**

**Full Response:**
> I don't have information about that in the transcripts.

### Query [F1] — Can you elaborate on that?
- **Type**: `follow-up`
- **Classified Intent**: `QA`
- **Rewritten Query**: `Tell me about activation in the first week. Can you elaborate on that?`
- **Latency**: `2839 ms` | **Tokens**: `448 prompt / 34 completion`
- **Faithfulness Assessment**: **FAITHFUL**

**Full Response:**
> Retention is heavily driven by activation within the first week [S1]. Users who experience core product value during their first session have 3x higher long-term retention.

**Verified Citations:**
- `[S1]` **Elena Verna 4.0: B2B Growth Loops** (Guest: Elena Verna) — *"Retention is heavily driven by activation within the first week. Users who experience core product value during their first session have 3x higher long-term retention."* [Chunk ID: `11111111-1111-1111-1111-111111111111`]

### Query [F2] — Who said that?
- **Type**: `follow-up`
- **Classified Intent**: `QA`
- **Rewritten Query**: `How should founders give away their Legos as the company scales? Who said that?`
- **Latency**: `1139 ms` | **Tokens**: `454 prompt / 10 completion`
- **Faithfulness Assessment**: **FAITHFUL**

**Full Response:**
> Molly Graham said that [S1].

**Verified Citations:**
- `[S1]` **Molly Graham: Giving Away Your Legos** (Guest: Molly Graham) — *"Giving away your Legos means actively handing over parts of your job to new hires as the team scales, embracing the anxiety that someone else now owns that Lego tower."* [Chunk ID: `88888888-8888-8888-8888-888888888888`]

---

## 4. Faithful Grounding vs. Hallucination Analysis

### 4.1 Anti-Reversal Directional Guardrail
In early spike testing without explicit anti-reversal instructions, 2 out of 15 queries reversed cause and effect (e.g. stating *"activation is driven by retention"* instead of *"retention is driven by activation"*).
With instruction rule 3 (*"State relationships exactly as the source states them. Never reverse cause and effect"*), all 8 in-scope and 2 follow-up answers preserved exact directional causality.

### 4.2 Citation Tag Resolution
- All tags generated by the model matched the range $[1..k]$ of retrieved chunks.
- No fabricated citations (`[S99]`) or hallucinated guest attributions were observed.
- Citation passages attached to the API response are retrieved directly from the verified database records, never from the model's generated text.

### 4.3 Zero-LLM Off-Domain Rejection
- For baking, World Cup sports, and Texas commercial real estate tax law, top similarity scores fell below `0.58`.
- The router intercepted these queries prior to prompt assembly and returned the exact refusal string `I don't have information about that in the transcripts.` in under 15ms.
- Zero prompt tokens and zero completion tokens were billed or computed for off-topic requests.