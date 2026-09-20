"""Safe server-side equivalent of frontend factor comparisons; no eval."""
import math
import operator
from dashboard_data import BOOLEAN_FIELDS

OPS={'>':operator.gt,'>=':operator.ge,'<':operator.lt,'<=':operator.le,'=':operator.eq,'!=':operator.ne}


def validate_rules(rules,match,catalog):
    if not isinstance(rules,list) or len(rules)>100 or match not in ['all','any']:raise ValueError('Invalid rules')
    for rule in rules:
        if not isinstance(rule,dict) or rule.get('key') not in catalog:raise ValueError('Unknown factor')
        if rule.get('enabled',True) is False:continue
        op=rule.get('op')
        if rule['key'] in BOOLEAN_FIELDS|{'technical_start','phase_match'}:
            if op not in ['true','false']:raise ValueError('Invalid boolean operator')
        elif op not in OPS and op!='between':raise ValueError('Invalid operator')
        elif rule.get('rhs')=='factor':
            if rule.get('factor') not in catalog or op=='between':raise ValueError('Invalid comparison factor')
        else:
            if not isinstance(rule.get('value'),(int,float)) or not math.isfinite(rule['value']):raise ValueError('Invalid threshold')
            if op=='between' and (not isinstance(rule.get('upper'),(int,float)) or not math.isfinite(rule['upper']) or rule['upper']<rule['value']):raise ValueError('Invalid range')


def rule_matches(row,rules,match='all'):
    statuses=[];missing=0
    for rule in rules:
        if rule.get('enabled') is False:continue
        left=row.get(rule['key']);right=row.get(rule.get('factor')) if rule.get('rhs')=='factor' else rule.get('value');op=rule['op']
        if left is None or op not in ['true','false'] and right is None:statuses.append(False);missing+=1;continue
        if op=='true':ok=left is True
        elif op=='false':ok=left is False
        elif op=='between':ok=right<=left<=rule['upper']
        else:ok=OPS[op](left,right)
        statuses.append(bool(ok))
    return (not statuses or (all(statuses) if match=='all' else any(statuses))),missing
