"""Conservative deterministic entity/polarity rules. Unknown paraphrases remain unknown."""
import re, difflib, math
from collections import Counter
WORDS={'zero':'0','one':'1','two':'2','three':'3','four':'4','five':'5','six':'6','seven':'7','eight':'8','nine':'9','ten':'10','twenty':'20','thirty':'30','forty':'40','fifty':'50','sixty':'60','seventy':'70','eighty':'80','ninety':'90','hundred':'100'}
ALIASES={'paid':'pay','payment':'pay','payments':'pay','completed':'complete','made':'complete','permitted':'allow','allowed':'allow','prohibited':'forbid','required':'require','days':'day','within':'within'}
STOP={'the','a','an','be','been','is','are','to','of'}
NEG=re.compile(r"\b(?:not|no|never|without|cannot|prohibited|forbidden)\b|n't\b",re.I)
ENTITY=re.compile(r'(?:[$€£₹]\s*)?\b\d[\d,]*(?:\.\d+)?(?:\s?(?:%|USD|EUR|GBP|INR|kg|km|cm|mm|days?|hours?))?\b|\b\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\b',re.I)

def normalize(s):
    tokens=re.findall(r"[\w]+|[$€£₹%]",s.lower())
    return ' '.join(WORDS.get(t,ALIASES.get(t,t)) for t in tokens if t not in STOP)

def facts(s):
    replaced=re.sub(r'\b('+ '|'.join(WORDS)+r')\b',lambda m:WORDS[m[0]],s.lower())
    return [re.sub(r'[,\s]','',x) for x in ENTITY.findall(replaced)]

def compare_semantics(a,b):
    na,nb=normalize(a),normalize(b)
    old,new=facts(a),facts(b)
    if old!=new:return dict(kind='NUMERIC_CHANGE',similarity=0.,certainty=.99,explanation='Numeric or unit-bearing tokens changed.',old_entities=old,new_entities=new)
    if bool(NEG.search(a))!=bool(NEG.search(b)):
        return dict(kind='POLARITY_CHANGE',similarity=0.,certainty=.9,explanation='Negation or prohibition changed; review sentence scope.')
    mod=lambda s:re.findall(r'\b(must|shall|should|may|can|will)\b',s.lower())
    if mod(a)!=mod(b):return dict(kind='OBLIGATION_CHANGE',similarity=0.,certainty=.85,explanation='Modal/obligation wording changed; equivalence is not assumed.')
    if a==b:return dict(kind='EXACT',similarity=1.,certainty=1.,explanation='Exact text.')
    if na==nb:return dict(kind='RULE_EQUIVALENT',similarity=1.,certainty=.8,explanation='Equivalent after the documented token and number normalization rules.')
    ca,cb=Counter(na.split()),Counter(nb.split());den=math.sqrt(sum(v*v for v in ca.values())*sum(v*v for v in cb.values()))
    lexical=sum(v*cb.get(k,0) for k,v in ca.items())/den if den else 0
    return dict(kind='MEANING_REVIEW',similarity=None,lexical_similarity=round(lexical,4),certainty=.5,explanation='Meaning is unresolved by deterministic rules; literal differences remain visible.')
