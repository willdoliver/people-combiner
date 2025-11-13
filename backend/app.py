from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd
import networkx as nx
from fuzzywuzzy import process
import io
import hashlib
import os
import logging

# Configure o logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')

# Configuração
FRONTEND_FOLDER = os.path.join(os.path.dirname(__file__), 'frontend')

app = Flask(__name__, static_folder=None)
CORS(app)

app.logger.info("Aplicação Flask iniciada com sucesso.")

def find_best_match(name, official_names, score_cutoff=85):
    if not name or pd.isna(name):
        return None
    try:
        matches = process.extract(name, official_names, limit=1)
        if not matches:
            return None
        match, score = matches[0]
        if score >= score_cutoff:
            return match
    except Exception as e:
        app.logger.error(f"Erro no fuzzywuzzy ao processar '{name}': {e}")
        return None
    return None

def get_name_map(voter_names, all_choices):
    app.logger.info("Iniciando mapeamento de nomes...")
    official_names = list(set(voter_names))
    unique_choices = list(set(c for c in all_choices if c and not pd.isna(c)))
    
    name_map = {}
    count = 0
    for choice in unique_choices:
        best_match = find_best_match(choice, official_names)
        if best_match:
            name_map[choice] = best_match
        count += 1
        if count % 50 == 0:
            app.logger.info(f"Mapeou {count}/{len(unique_choices)} nomes...")
            
    for name in official_names:
        name_map[name] = name
        
    app.logger.info("Mapeamento de nomes concluído.")
    return name_map

def build_graph(voter_names, votes_map):
    G = nx.Graph()
    G.add_nodes_from(voter_names)
    
    for voter, choices in votes_map.items():
        for choice in choices:
            if not G.has_node(voter) or not G.has_node(choice):
                continue
            is_mutual = voter in votes_map.get(choice, []) and choice in votes_map.get(voter, [])
            if is_mutual:
                G.add_edge(voter, choice, weight=2)
            else:
                if not G.has_edge(voter, choice):
                    G.add_edge(voter, choice, weight=1)
    return G

def get_affinity(G, student, group):
    score = 0
    for member in group:
        if G.has_edge(student, member):
            score += G[student][member]['weight']
    return score

def is_forbidden(student, group, forbidden_pairs):
    for member in group:
        if frozenset([student, member]) in forbidden_pairs:
            return True
    return False

def hex_to_rgb(hex_code):
    hex_code = hex_code.lstrip('#')
    return tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4))

def get_luminance(hex_code):
    try:
        r, g, b = hex_to_rgb(hex_code)
        return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    except Exception:
        return 0.5 

def generate_random_color(text_seed):
    hash_object = hashlib.md5(text_seed.encode())
    hex_dig = hash_object.hexdigest()
    return "#" + hex_dig[:6]

def generate_dot_graph(G, final_groups, forbidden_pairs):
    dot_code = ["digraph G {"]
    dot_code.append("    layout=neato;")
    dot_code.append("    overlap=false;")
    dot_code.append("    splines=true;")
    dot_code.append("    node [shape=box, style=\"rounded,filled\", fontsize=10];")
    dot_code.append("    edge [fontsize=8, dir=none];") 

    student_to_style = {}
    colors = [
        "#A8E6CF", "#D7BDE2", "#F9E79F", "#F5B7B1", "#AED6F1", "#A2D9CE", 
        "#FAD7A0", "#F1948A", "#D2B4DE", "#A9CCE3", "#ABEBC6", "#FADBD8", 
        "#AEB6BF", "#E6B0AA", "#EDBB99", "#D5DBDB", "#FDEDEC", "#FADADD", 
        "#E8DAEF", "#D4E6F1", "#D1F2EB", "#FCF3CF", "#FDEBD0", "#F6DDCC",
        "#FFC3A0", "#FFAB91", "#FF8A80", "#FF80AB", "#EA80FC", "#B388FF",
        "#8C9EFF", "#82B1FF", "#80D8FF", "#84FFFF", "#A7FFEB", "#B9F6CA",
        "#CCFF90", "#F4FF81", "#FFFF8D", "#FFD180", "#FFAB40", "#FF6E40"
    ]
    
    for i, group in enumerate(final_groups):
        font_color = "black" 
        if i < len(colors):
            group_color = colors[i]
        else:
            group_color = generate_random_color(group[0] if group else "default") 
            if get_luminance(group_color) < 0.45:
                font_color = "white"
        for student in group:
            student_to_style[student] = (group_color, font_color)

    for student in G.nodes():
        style = student_to_style.get(student, ("#EEEEEE", "black"))
        color = style[0]
        fontcolor = style[1]
        dot_code.append(f"    \"{student}\" [fillcolor=\"{color}\", fontcolor=\"{fontcolor}\"];")
    
    for u, v, data in G.edges(data=True):
        edge_color = "gray"
        penwidth = "1.0"
        if data['weight'] == 2:
            edge_color = "blue"
            penwidth = "2.5"
        if frozenset([u,v]) in forbidden_pairs:
            edge_color = "red"
            penwidth = "3.0"
            dot_code.append(f"    \"{u}\" -> \"{v}\" [color=\"{edge_color}\", penwidth={penwidth}, style=dashed, tooltip=\"Restrição: NÃO pode ficar junto!\"];")
        else:
            dot_code.append(f"    \"{u}\" -> \"{v}\" [color=\"{edge_color}\", penwidth={penwidth}];")

    dot_code.append("}")
    return "\n".join(dot_code)

def find_best_candidate(unassigned_students, group, G, forbidden_pairs, 
                        balance_gender=False, gender_map=None, balance_weight=0.5):
    
    if not unassigned_students:
        return None

    possible_candidates = [s for s in unassigned_students if not is_forbidden(s, group, forbidden_pairs)]
    
    if not possible_candidates:
        return None 

    # Lógica sem balanceamento
    if not balance_gender or not gender_map:
        best_candidate = None
        max_affinity = -1 
        
        for student in possible_candidates:
            affinity = get_affinity(G, student, group)
            if affinity > max_affinity: 
                max_affinity = affinity
                best_candidate = student
        
        return best_candidate 

    # Lógica com balanceamento
    current_genders = [gender_map.get(s) for s in group if s in gender_map]
    current_m = current_genders.count('M')
    current_f = current_genders.count('F')
    
    candidates_m = [s for s in possible_candidates if gender_map.get(s) == 'M']
    candidates_f = [s for s in possible_candidates if gender_map.get(s) == 'F']
    candidates_unknown = [s for s in possible_candidates if gender_map.get(s) not in ['M', 'F']]

    scores_m = {s: get_affinity(G, s, group) for s in candidates_m}
    scores_f = {s: get_affinity(G, s, group) for s in candidates_f}
    scores_unknown = {s: get_affinity(G, s, group) for s in candidates_unknown}

    best_m = max(scores_m, key=scores_m.get) if scores_m else None
    best_f = max(scores_f, key=scores_f.get) if scores_f else None
    best_unknown = max(scores_unknown, key=scores_unknown.get) if scores_unknown else None
    
    affinity_m = scores_m.get(best_m, -1)
    affinity_f = scores_f.get(best_f, -1)
    affinity_unknown = scores_unknown.get(best_unknown, -1)

    best_options = []
    if best_m and affinity_m > 0:
        best_options.append((best_m, affinity_m, 'M'))
    if best_f and affinity_f > 0:
        best_options.append((best_f, affinity_f, 'F'))
    if best_unknown and affinity_unknown > 0:
        best_options.append((best_unknown, affinity_unknown, 'U'))
        
    if not best_options:
        if best_unknown: return best_unknown
        if best_m: return best_m
        if best_f: return best_f
        return None 

    weighted_scores = []
    for student, affinity, gender in best_options:
        weight = 1.0 
        if gender == 'M':
            if current_m > current_f: 
                weight = balance_weight
        elif gender == 'F':
            if current_f > current_m: 
                weight = balance_weight
        
        weighted_scores.append((student, affinity * weight))
    
    best_candidate, best_weighted_score = max(weighted_scores, key=lambda item: item[1])
    return best_candidate

# Rotas do Flask

@app.route('/process', methods=['POST'])
def process_csv():
    app.logger.info("-----------------------------------")
    app.logger.info("A ROTA /process FOI CHAMADA!")
    app.logger.info("-----------------------------------")
    
    try:
        # Ler Dados do Formulário
        csv_file = request.files['csv_file']
        group_size = int(request.form['group_size'])
        restrictions_text = request.form['restrictions']
        balance_gender = request.form.get('balance_gender') == 'true'

        app.logger.info(f"Nome do arquivo: {csv_file.filename}, Tamanho: {group_size}, Balancear: {balance_gender}")

        if not csv_file:
            return jsonify({"error": "Nenhum arquivo CSV enviado."}), 400

        # Ler e Processar o CSV
        data = io.StringIO(csv_file.stream.read().decode("UTF-8"))
        df = pd.read_csv(data)
        app.logger.info("Arquivo CSV lido com sucesso.")

        # Encontrar Colunas
        name_col = next((col for col in df.columns if 'nome' in col.lower() and 'usuário' not in col.lower()), None)
        option_cols = [col for col in df.columns if 'opção' in col.lower() or 'escreva' in col.lower()]
        gender_col = next((col for col in df.columns if 'gênero' in col.lower() or 'sexo' in col.lower()), None)

        if not name_col:
            app.logger.error("Coluna 'Nome' não encontrada.")
            return jsonify({"error": "Não foi possível encontrar a coluna 'Nome' ou similar."}), 400
        if not option_cols:
            app.logger.error("Colunas de 'opção' não encontradas.")
            return jsonify({"error": "Não foi possível encontrar colunas de 'opção' ou 'escreva'."}), 400

        if balance_gender and not gender_col:
            app.logger.error("Balanceamento pedido, mas coluna 'Gênero' não encontrada.")
            return jsonify({"error": "Para balancear, o CSV precisa de uma coluna chamada 'Gênero' ou 'Sexo', preenchida com 'Masculino' ou 'Feminino'."}), 400

        # Limpeza e Mapeamento
        voter_names = list(df[name_col].dropna().unique())
        all_choices = []
        for col in option_cols:
            all_choices.extend(list(df[col].dropna().unique()))

        name_map = get_name_map(voter_names, all_choices)
        valid_official_names = set(voter_names).union(set(name_map.values()))

        votes_map = {}
        student_gender_map = {} 

        for _, row in df.iterrows():
            voter_raw = row[name_col]
            voter_official = name_map.get(voter_raw)
            if not voter_official: 
                continue
            
            voter_choices = []
            for col in option_cols:
                choice_raw = row[col]
                choice_official = name_map.get(choice_raw)
                if choice_official and choice_official != voter_official:
                    voter_choices.append(choice_official)
            votes_map[voter_official] = list(set(voter_choices)) 

            if balance_gender and gender_col and pd.notna(row[gender_col]):
                gender_raw = str(row[gender_col]).lower()
                if 'm' in gender_raw or 'masculino' in gender_raw:
                    student_gender_map[voter_official] = 'M'
                elif 'f' in gender_raw or 'w' in gender_raw or 'feminino' in gender_raw: 
                    student_gender_map[voter_official] = 'F'
                else:
                    student_gender_map[voter_official] = 'U'
        
        app.logger.info(f"Mapa de votos e mapa de gêneros construídos. {len(student_gender_map)} gêneros mapeados.")

        # Construir Grafo e Restrições
        all_students_in_graph = set(votes_map.keys())
        for choices in votes_map.values():
            all_students_in_graph.update(choices)

        all_students_in_graph = [s for s in all_students_in_graph if s in valid_official_names]
        G = build_graph(all_students_in_graph, votes_map)
        app.logger.info("Grafo de afinidade construído.")

        forbidden_pairs = set()
        for line in restrictions_text.splitlines():
            if line.strip():
                names = [name.strip() for name in line.split(',')]
                if len(names) >= 2:
                    name1_official = name_map.get(names[0])
                    name2_official = name_map.get(names[1])
                    if name1_official and name2_official:
                        forbidden_pairs.add(frozenset([name1_official, name2_official]))
        app.logger.info(f"{len(forbidden_pairs)} pares de restrição processados.")
        
        # Algoritmo de Agrupamento
        unassigned_students = set(all_students_in_graph) 
        final_groups = []
        warnings = []
        all_edges = sorted(G.edges(data=True), key=lambda x: x[2]['weight'], reverse=True)
        
        app.logger.info("Iniciando Fase do agrupamento...")
        for u, v, data in all_edges:
            if u in unassigned_students and v in unassigned_students:
                if frozenset([u, v]) not in forbidden_pairs:
                    new_group = [u, v]
                    unassigned_students.remove(u)
                    unassigned_students.remove(v)
                    
                    while len(new_group) < group_size:
                        best_candidate = find_best_candidate(
                            unassigned_students, new_group, G, forbidden_pairs,
                            balance_gender, student_gender_map
                        )
                        if best_candidate:
                            new_group.append(best_candidate)
                            unassigned_students.remove(best_candidate)
                        else:
                            break 
                    final_groups.append(new_group)
        
        app.logger.info(f"Fase 1 concluída. {len(final_groups)} grupos formados. {len(unassigned_students)} alunos restantes.")
        app.logger.info("Iniciando Fase do agrupamento...")
        
        for student in list(unassigned_students): 
            if student not in unassigned_students: 
                 continue
            
            best_group_to_join = None
            max_affinity = -1 
            
            for group in final_groups:
                if len(group) < group_size and not is_forbidden(student, group, forbidden_pairs):
                    affinity = get_affinity(G, student, group)
                    
                    if balance_gender and gender_map:
                        current_genders = [student_gender_map.get(s) for s in group if s in student_gender_map]
                        current_m = current_genders.count('M')
                        current_f = current_genders.count('F')
                        student_gender = student_gender_map.get(student)
                        
                        if student_gender == 'M' and current_m > current_f:
                            affinity *= 0.5 
                        elif student_gender == 'F' and current_f > current_m:
                            affinity *= 0.5
                    
                    if affinity > max_affinity:
                        max_affinity = affinity
                        best_group_to_join = group
            
            if best_group_to_join:
                best_group_to_join.append(student)
                unassigned_students.remove(student)

        app.logger.info("Iniciando Fase 3 do agrupamento...")
        while unassigned_students:
            student = unassigned_students.pop()
            new_group = [student]
            
            while len(new_group) < group_size:
                best_candidate = find_best_candidate(
                    unassigned_students, new_group, G, forbidden_pairs,
                    balance_gender, student_gender_map
                )
                if best_candidate:
                    new_group.append(best_candidate)
                    unassigned_students.remove(best_candidate)
                else:
                    break 
            
            final_groups.append(new_group)
            if len(new_group) == 1:
                 warnings.append(f"Grupo {len(final_groups)} ({new_group[0]}) possui apenas 1 membro, pois não foi possível alocá-lo.")
            elif balance_gender and len(new_group) < group_size:
                 warnings.append(f"Grupo {len(final_groups)} ({', '.join(new_group)}) foi formado com menos membros que o desejado.")

        app.logger.info("Fase 3 concluída. Agrupamento finalizado.")
        
        dot_code = generate_dot_graph(G, final_groups, forbidden_pairs)
        app.logger.info("Código DOT do grafo gerado.")
        
        return jsonify({"groups": final_groups, "warnings": warnings, "dot_code": dot_code})

    except Exception as e:
        app.logger.error(f"ERRO CRÍTICO NA ROTA /process: {e}", exc_info=True)
        return jsonify({"error": f"Ocorreu um erro interno: {str(e)}"}), 500

@app.route('/')
def index():
    return send_from_directory(FRONTEND_FOLDER, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(FRONTEND_FOLDER, path)