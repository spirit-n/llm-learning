from __future__ import annotations

from .models import Document, GoldenCase


DOCUMENTS = [
    Document(doc_id="revenue-v2", title="营业收入", source="metric-spec-v2", version="2.0", tenant="demo", text="# 当前定义\n营业收入是不含税支付金额扣除已完成退款。生效日期为 2025-03-01。"),
    Document(doc_id="revenue-v1", title="营业收入旧版", source="metric-spec-v1", version="1.0", tenant="demo", is_latest=False, text="# 旧版定义\n营业收入曾定义为含税订单金额且不扣退款。"),
    Document(doc_id="conversion-v2", title="转化率", source="metric-spec-v2", version="2.0", tenant="demo", text="# 当前定义\n转化率等于支付用户数除以独立访客数。"),
    Document(doc_id="error-e102", title="错误码 E102", source="ops-guide-v3", version="3.0", tenant="demo", text="# E102\n错误码 E102 表示上游请求超时。先检查依赖服务延迟，再按请求 ID 查询日志。"),
    Document(doc_id="inventory-v2", title="可用库存", source="metric-spec-v2", version="2.0", tenant="demo", text="# 当前定义\n可用库存等于在手数量减去已预占数量。"),
    Document(doc_id="rag-guide", title="RAG 基础", source="rag-guide", version="1.0", tenant="demo", text="# 幻觉\nRAG 仍可能产生幻觉，因为召回证据可能缺失、冲突或被模型错误解释。"),
    Document(doc_id="private-policy", title="内部折扣", source="private-policy", version="1.0", tenant="acme", text="# 保密折扣\n企业专属折扣为 35%，只允许 acme 租户查看。"),
]


GOLDEN_CASES = [
    GoldenCase(case_id="q1", question="现在营收怎么定义？", evidence_chunk_ids=["revenue-v2#h1"], tags=["synonym", "version"]),
    GoldenCase(case_id="q2", question="支付用户和访客怎样计算转化率？", evidence_chunk_ids=["conversion-v2#h1"], tags=["definition"]),
    GoldenCase(case_id="q3", question="E102 是什么报错？", evidence_chunk_ids=["error-e102#h1"], tags=["exact-term"]),
    GoldenCase(case_id="q4", question="存货里哪些数量算可用？", evidence_chunk_ids=["inventory-v2#h1"], tags=["synonym"]),
    GoldenCase(case_id="q5", question="为什么检索增强仍会胡编？", evidence_chunk_ids=["rag-guide#h1"], tags=["semantic"]),
]

