from __future__ import annotations

COURSE_NAMES={1:"1 курс",2:"2 курс",3:"3 курс",4:"4 курс"}
SUBJECT_NAMES={"PHYSICS":"Физика"}
PHYSICS_COURSES=(1,2)

COLLEGE_LIBRARY={
1:{"PHYSICS":{
"KIN":{"title":"Кинематика","text":"🚗 1 КУРС · КИНЕМАТИКА\n\nv = s/t\ns = vt\nx = x₀ + vt\nv = v₀ + at\ns = v₀t + at²/2\nv² − v₀² = 2as\naц = v²/R = ω²R\nω = 2π/T = 2πν"},
"DYN":{"title":"Динамика и законы Ньютона","text":"⚙️ 1 КУРС · ДИНАМИКА\n\nΣF = ma\nFтяж = mg\nFупр = kΔx\nFтр = μN\nF = Gm₁m₂/r²\np = mv\nFΔt = Δp\nΣpдо = Σpпосле"},
"ENERGY":{"title":"Работа, мощность и энергия","text":"🔋 1 КУРС · ЭНЕРГИЯ\n\nA = Fs cosα\nP = A/t = Fv cosα\nEк = mv²/2\nEп = mgh\nEпруж = kx²/2\nη = Aпол/Aзат·100%"},
"MOLECULAR":{"title":"Молекулярная физика","text":"🌡 1 КУРС · МКТ\n\nν = m/M = N/Nₐ\npV = νRT\np₁V₁/T₁ = p₂V₂/T₂\npV = const\nV/T = const\np/T = const\nEср = 3kT/2"},
"THERMO":{"title":"Термодинамика","text":"🔥 1 КУРС · ТЕРМОДИНАМИКА\n\nQ = cmΔT\nQ = λm\nQ = Lm\nQ = ΔU + A\nU = 3νRT/2\nA = pΔV\nη = (Q₁−Q₂)/Q₁·100%"},
"DC":{"title":"Постоянный электрический ток","text":"🔌 1 КУРС · ПОСТОЯННЫЙ ТОК\n\nI = q/t\nI = U/R\nR = ρl/S\nP = UI = I²R = U²/R\nA = UIt\nQ = I²Rt\nI = ε/(R+r)\nU = ε−Ir"},
}},
2:{"PHYSICS":{
"OSC":{"title":"Колебания и волны","text":"🌊 2 КУРС · КОЛЕБАНИЯ И ВОЛНЫ\n\nν = 1/T\nω = 2πν\nx = A cos(ωt+φ)\nTпруж = 2π√(m/k)\nTмаят = 2π√(l/g)\nv = λν"},
"ELECTRO":{"title":"Электростатика","text":"⚡ 2 КУРС · ЭЛЕКТРОСТАТИКА\n\nF = k|q₁q₂|/r²\nE = F/q = k|Q|/r²\nU = φ₁−φ₂\nA = qU\nC = q/U\nW = CU²/2"},
"MAG":{"title":"Магнитное поле","text":"🧲 2 КУРС · МАГНИТНОЕ ПОЛЕ\n\nFА = BIl sinα\nFЛ = |q|vB sinα\nR = mv/(|q|B)\nΦ = BS cosα"},
"IND":{"title":"Электромагнитная индукция","text":"🔄 2 КУРС · ИНДУКЦИЯ\n\nΦ = BS cosα\nε = −ΔΦ/Δt\nε = −NΔΦ/Δt\nεсам = −LΔI/Δt\nW = LI²/2"},
"OPTICS":{"title":"Оптика","text":"🔎 2 КУРС · ОПТИКА\n\nα = β\nn₁sinα = n₂sinβ\nn = c/v\n1/F = 1/d + 1/f\nD = 1/F\nΓ = f/d\nd sinφ = kλ"},
}},
}

def course_label(course:int)->str:return COURSE_NAMES.get(int(course),f"{course} курс")
def courses(current=None):
    out=list(PHYSICS_COURSES)
    if current in out:
        out.remove(current);out.insert(0,current)
    return out

def subjects(course:int):return [(k,SUBJECT_NAMES.get(k,k)) for k in COLLEGE_LIBRARY.get(int(course),{})]
def topics(course:int,subject:str):return [(k,v.get("title",k)) for k,v in COLLEGE_LIBRARY.get(int(course),{}).get(str(subject),{}).items()]
def topic(course:int,subject:str,key:str):
    item=COLLEGE_LIBRARY.get(int(course),{}).get(str(subject),{}).get(str(key));return item.get("text") if item else None

def physics_available(course:int)->bool:return int(course) in PHYSICS_COURSES
