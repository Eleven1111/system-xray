"""明确的报告 schema 与运行时契约投影。

JSON Schema 是交付报告形状；运行时契约以 `dimension_scores` 和对象账本为核心。
两者不再各自声称可以直接互换：所有跨边界输入先经本模块转换。
"""

_DIMENSION_KEYS = {
    'd1_boundary': 'D1', 'd2_incentive': 'D2', 'd3_information': 'D3',
    'd4_temporal': 'D4', 'd5_legitimacy': 'D5', 'd6_coupling': 'D6',
    'd7_power': 'D7',
}


def to_runtime(document: dict) -> dict:
    """将旧报告 schema 的 dimensions 投影为运行时分析；新契约对象原样保留。"""
    if not isinstance(document, dict) or 'dimension_scores' in document:
        return document
    dimensions = document.get('dimensions')
    if not isinstance(dimensions, dict):
        return document
    out = dict(document)
    out['dimension_scores'] = {
        runtime: dimensions.get(schema_key, {}).get('score')
        for schema_key, runtime in _DIMENSION_KEYS.items()
        if isinstance(dimensions.get(schema_key), dict)
    }
    metadata = document.get('metadata') or {}
    out.setdefault('output_mode', 'full')
    if metadata.get('analysis_date'):
        out.setdefault('process_metadata', {'as_of_date': metadata['analysis_date']})
    return out


def to_document(analysis: dict, system_name: str = 'unspecified',
                system_type: str = 'other', analysis_date: str = '1970-01-01') -> dict:
    """将运行时分析投影为 Draft7 报告文档，供 schema 校验和交换使用。"""
    if not isinstance(analysis, dict):
        return analysis
    scores = analysis.get('dimension_scores') or {}
    dimensions = {}
    for schema_key, runtime in _DIMENSION_KEYS.items():
        dimensions[schema_key] = {'score': scores.get(runtime, 'unknown'),
                                  'trajectory': 'stable', 'key_findings': [], 'evidence': []}
    contract = analysis.get('analysis_contract') or {}
    return {
        **analysis,
        'schema_version': '2.0',
        'metadata': analysis.get('metadata') or {
            'system_name': analysis.get('system_name', system_name),
            'system_type': analysis.get('system_type', system_type),
            'analysis_date': analysis.get('analysis_date', analysis_date),
            'analyst_confidence': 'low', 'information_sources': [],
        },
        'analysis_contract': contract,
        'cartography': analysis.get('cartography') or {},
        'dimensions': dimensions,
        'cross_dimensional': analysis.get('cross_dimensional') or {},
        'risk_nodes': analysis.get('risk_nodes') or [],
        'scenarios': analysis.get('scenarios') or [],
        'prescriptions': analysis.get('prescriptions') or [],
        'predictions': analysis.get('predictions') or [],
    }
