from __future__ import annotations

COURSE_NAMES={1:"1 курс",2:"2 курс",3:"3 курс",4:"4 курс"}
SUBJECT_NAMES={"PHYSICS":"Физика","CHEMISTRY":"Химия"}

COLLEGE_LIBRARY={
1:{
"PHYSICS":{
"KIN":{"title":"Кинематика","text":"🚗 1 КУРС · КИНЕМАТИКА\n\nv = s/t\ns = vt\nx = x₀ + vt\nv = v₀ + at\ns = v₀t + at²/2\nv² − v₀² = 2as\naц = v²/R = ω²R\nω = 2π/T = 2πν"},
"DYN":{"title":"Динамика и законы Ньютона","text":"⚙️ 1 КУРС · ДИНАМИКА\n\nΣF = ma\nFтяж = mg\nFупр = kΔx\nFтр = μN\nF = Gm₁m₂/r²\np = mv\nFΔt = Δp\nΣpдо = Σpпосле"},
"ENERGY":{"title":"Работа, мощность и энергия","text":"🔋 1 КУРС · ЭНЕРГИЯ\n\nA = Fs cosα\nP = A/t = Fv cosα\nEк = mv²/2\nEп = mgh\nEпруж = kx²/2\nη = Aпол/Aзат·100%"},
"MOLECULAR":{"title":"Молекулярная физика","text":"🌡 1 КУРС · МКТ\n\nν = m/M = N/Nₐ\npV = νRT\np₁V₁/T₁ = p₂V₂/T₂\npV = const\nV/T = const\np/T = const\nEср = 3kT/2"},
"THERMO":{"title":"Термодинамика","text":"🔥 1 КУРС · ТЕРМОДИНАМИКА\n\nQ = cmΔT\nQ = λm\nQ = Lm\nQ = ΔU + A\nU = 3νRT/2\nA = pΔV\nη = (Q₁−Q₂)/Q₁·100%"},
"DC":{"title":"Постоянный электрический ток","text":"🔌 1 КУРС · ПОСТОЯННЫЙ ТОК\n\nI = q/t\nI = U/R\nR = ρl/S\nP = UI = I²R = U²/R\nA = UIt\nQ = I²Rt\nI = ε/(R+r)\nU = ε−Ir"},
},
"CHEMISTRY":{
"ATOM":{"title":"Строение атома","text":"⚛️ 1 КУРС · СТРОЕНИЕ АТОМА\n\nZ = число протонов\nA = Z + N\nN = A − Z\nДля нейтрального атома число электронов = Z."},
"MOLE":{"title":"Моль и количество вещества","text":"⚗️ 1 КУРС · КОЛИЧЕСТВО ВЕЩЕСТВА\n\nν = m/M\nm = νM\nν = N/Nₐ\nN = νNₐ\nV = νVₘ\nVₘ ≈ 22,4 л/моль"},
"STOICH":{"title":"Стехиометрия","text":"🧪 1 КУРС · СТЕХИОМЕТРИЯ\n\n1. Расставить коэффициенты.\n2. ν = m/M.\n3. Использовать отношение коэффициентов.\n4. m = νM, V = νVₘ.\nη = mпракт/mтеор·100%"},
"SOLUTIONS":{"title":"Растворы и концентрации","text":"💧 1 КУРС · РАСТВОРЫ\n\nω = mвещ/mр-ра\nmвещ = ωmр-ра\nC = ν/V\nν = CV\nПри разбавлении: C₁V₁ = C₂V₂"},
}},
2:{
"PHYSICS":{
"OSC":{"title":"Колебания и волны","text":"🌊 2 КУРС · КОЛЕБАНИЯ И ВОЛНЫ\n\nν = 1/T\nω = 2πν\nx = A cos(ωt+φ)\nTпруж = 2π√(m/k)\nTмаят = 2π√(l/g)\nv = λν"},
"ELECTRO":{"title":"Электростатика","text":"⚡ 2 КУРС · ЭЛЕКТРОСТАТИКА\n\nF = k|q₁q₂|/r²\nE = F/q = k|Q|/r²\nU = φ₁−φ₂\nA = qU\nC = q/U\nW = CU²/2"},
"MAG":{"title":"Магнитное поле","text":"🧲 2 КУРС · МАГНИТНОЕ ПОЛЕ\n\nFА = BIl sinα\nFЛ = |q|vB sinα\nR = mv/(|q|B)\nΦ = BS cosα"},
"IND":{"title":"Электромагнитная индукция","text":"🔄 2 КУРС · ИНДУКЦИЯ\n\nΦ = BS cosα\nε = −ΔΦ/Δt\nε = −NΔΦ/Δt\nεсам = −LΔI/Δt\nW = LI²/2"},
"OPTICS":{"title":"Оптика","text":"🔎 2 КУРС · ОПТИКА\n\nα = β\nn₁sinα = n₂sinβ\nn = c/v\n1/F = 1/d + 1/f\nD = 1/F\nΓ = f/d\nd sinφ = kλ"},
},
"CHEMISTRY":{
"RATE":{"title":"Скорость реакции","text":"⏱ 2 КУРС · СКОРОСТЬ РЕАКЦИИ\n\nv = ΔC/Δt\nПравило Вант-Гоффа: v₂/v₁ = γ^((T₂−T₁)/10)."},
"EQ":{"title":"Химическое равновесие","text":"⚖️ 2 КУРС · РАВНОВЕСИЕ\n\nДля aA+bB⇄cC+dD:\nKc = [C]^c[D]^d / ([A]^a[B]^b)\nПринцип Ле Шателье: равновесие смещается против внешнего воздействия."},
"PH":{"title":"Кислоты, основания и pH","text":"🧪 2 КУРС · pH\n\npH = −lg[H⁺]\npOH = −lg[OH⁻]\npH + pOH = 14\npH<7 кислая, pH=7 нейтральная, pH>7 щелочная среда."},
"REDOX":{"title":"ОВР и электронный баланс","text":"🔋 2 КУРС · ОВР\n\nОкисление — отдача e⁻.\nВосстановление — принятие e⁻.\nЧисло отданных электронов = числу принятых."},
}},
3:{
"PHYSICS":{
"AC":{"title":"Переменный ток","text":"〰️ 3 КУРС · ПЕРЕМЕННЫЙ ТОК\n\nu = Um sinωt\ni = Im sinωt\nU = Um/√2\nI = Im/√2\nXL = ωL\nXC = 1/(ωC)\nZ = √(R²+(XL−XC)²)\nI = U/Z"},
"TRANSFORMER":{"title":"Трансформаторы","text":"⚡ 3 КУРС · ТРАНСФОРМАТОР\n\nU₁/U₂ = N₁/N₂\nI₁/I₂ = N₂/N₁\nP₁ ≈ P₂\nη = P₂/P₁·100%\nPпот = I²R"},
"SEMICONDUCTOR":{"title":"Полупроводники и электроника","text":"💻 3 КУРС · ЭЛЕКТРОНИКА\n\nI = U/R\nP = UI\nДиод проводит преимущественно в прямом направлении.\nIэ = Iк + Iб\nβ = Iк/Iб"},
"EMW":{"title":"Электромагнитные волны","text":"📡 3 КУРС · ЭМ-ВОЛНЫ\n\nc = λν\nc ≈ 3·10⁸ м/с\nE = hν = hc/λ\np = h/λ"},
},
"CHEMISTRY":{
"ORGANIC":{"title":"Основы органической химии","text":"🧬 3 КУРС · ОРГАНИКА\n\nАлканы: CₙH₂ₙ₊₂\nАлкены: CₙH₂ₙ\nАлкины: CₙH₂ₙ₋₂\nСпирты содержат −OH, карбоновые кислоты −COOH."},
"HYDROCARBONS":{"title":"Углеводороды","text":"⛽ 3 КУРС · УГЛЕВОДОРОДЫ\n\nГорение: CxHy + O₂ → CO₂ + H₂O.\nДля расчётов использовать ν = m/M и коэффициенты уравнения."},
"OXYGEN":{"title":"Кислородсодержащие органические вещества","text":"🧪 3 КУРС · КИСЛОРОДСОДЕРЖАЩИЕ СОЕДИНЕНИЯ\n\nСпирты R−OH\nАльдегиды R−CHO\nКислоты R−COOH\nЭтерификация: кислота + спирт ⇄ сложный эфир + вода."},
"POLYMERS":{"title":"Полимеры","text":"🧵 3 КУРС · ПОЛИМЕРЫ\n\nПолимеризация: nM → (−M−)ₙ.\nСтепень полимеризации n ≈ Mполимера/Mзвена."},
}},
4:{
"PHYSICS":{
"QUANTUM":{"title":"Квантовая физика","text":"✨ 4 КУРС · КВАНТОВАЯ ФИЗИКА\n\nE = hν = hc/λ\np = h/λ\nФотоэффект: hν = Aвых + mv²/2\nКрасная граница: ν₀ = Aвых/h"},
"ATOM":{"title":"Атомная физика","text":"⚛️ 4 КУРС · АТОМНАЯ ФИЗИКА\n\nПостулат Бора: hν = E₂−E₁\nДля фотона: E = hν.\nСпектральные линии соответствуют переходам между энергетическими уровнями."},
"NUCLEAR":{"title":"Ядерная физика","text":"☢️ 4 КУРС · ЯДЕРНАЯ ФИЗИКА\n\nA = Z + N\nΔm = Zmp + Nmn − mядра\nEсв = Δmc²\nN = N₀·2^(−t/T₁/₂)\nAакт = λN"},
"REL":{"title":"Элементы специальной теории относительности","text":"🚀 4 КУРС · СТО\n\nγ = 1/√(1−v²/c²)\nE = mc²\nE² = p²c² + m²c⁴\nПри v≪c классическая механика остаётся хорошим приближением."},
},
"CHEMISTRY":{
"ELECTROCHEM":{"title":"Электрохимия","text":"🔋 4 КУРС · ЭЛЕКТРОХИМИЯ\n\nQ = It\nν(e⁻) = Q/F\nF ≈ 96500 Кл/моль\nЗакон Фарадея: m = MIt/(zF)."},
"THERMOCHEM":{"title":"Термохимия","text":"🔥 4 КУРС · ТЕРМОХИМИЯ\n\nΔH = Hпрод − Hисх\nЭкзотермический процесс: ΔH<0.\nЭндотермический: ΔH>0.\nПо закону Гесса тепловой эффект зависит только от начального и конечного состояния."},
"ANALYTICAL":{"title":"Основы аналитической химии","text":"🔬 4 КУРС · АНАЛИТИЧЕСКАЯ ХИМИЯ\n\nC = ν/V\nν = CV\nПри титровании для реакции 1:1: C₁V₁ = C₂V₂.\nДля других коэффициентов использовать отношение стехиометрических коэффициентов."},
"MATERIALS":{"title":"Химия материалов","text":"🏗 4 КУРС · МАТЕРИАЛЫ\n\nМассовая доля компонента: ω = mкомп/mсмеси.\nВыход продукта: η = mпракт/mтеор·100%.\nКоррозия — самопроизвольное разрушение материалов при химическом или электрохимическом взаимодействии со средой."},
}},
}

def course_label(course:int)->str:return COURSE_NAMES.get(int(course),f"{course} курс")
def courses(current=None):
    out=[1,2,3,4]
    if current in out:
        out.remove(current);out.insert(0,current)
    return out

def subjects(course:int):return [(k,SUBJECT_NAMES.get(k,k)) for k in COLLEGE_LIBRARY.get(int(course),{})]
def topics(course:int,subject:str):return [(k,v.get("title",k)) for k,v in COLLEGE_LIBRARY.get(int(course),{}).get(str(subject),{}).items()]
def topic(course:int,subject:str,key:str):
    item=COLLEGE_LIBRARY.get(int(course),{}).get(str(subject),{}).get(str(key));return item.get("text") if item else None
