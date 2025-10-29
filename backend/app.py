from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import networkx as nx
from fuzzywuzzy import process
import io
import math
import hashlib # Para gerar cores consistentes para os grupos

app = Flask(__name__)
CORS(app)  # Permite que o frontend se comunique com o backend

# --- Funções de Limpeza e Normalização ---

def find_best_match(name, official_names, score_cutoff=85):
    if not name or pd.isna(name):
        return None
    match, score = process.extractOne(name, official_names)
    if score >= score_cutoff:
        return match
    return None

def get_name_map(voter_names, all_choices):
    official_names = list(set(voter_names))
    unique_choices = list(set(c for c in all_choices if c and not pd.isna(c)))
    
    name_map = {}
    for choice in unique_choices:
        best_match = find_best_match(choice, official_names)
        if best_match:
            name_map[choice] = best_match
            
    for name in official_names:
        name_map[name] = name
        
    return name_map

# --- Funções do Algoritmo de Grafo ---

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
                elif G.has_edge(voter, choice) and G[voter][choice]['weight'] == 1:
                    pass
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

# --- Geração do Código DOT do Grafo (COM LÓGICA DE COR) ---

def hex_to_rgb(hex_code):
    """Converte #RRGGBB para (R, G, B) tupla."""
    hex_code = hex_code.lstrip('#')
    return tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4))

def get_luminance(hex_code):
    """Calcula a luminância percebida de uma cor hex (0=preto, 1=branco)."""
    try:
        r, g, b = hex_to_rgb(hex_code)
        # Fórmula de luminância (padrão ITU-R BT.709)
        return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    except Exception:
        return 0.5 # Retorna um valor neutro em caso de erro

def generate_random_color(text_seed):
    """Gera uma cor hex a partir de um texto."""
    hash_object = hashlib.md5(text_seed.encode())
    hex_dig = hash_object.hexdigest()
    return "#" + hex_dig[:6]

def generate_dot_graph(G, final_groups, forbidden_pairs):
    dot_code = ["digraph G {"]
    dot_code.append("    layout=neato;")
    dot_code.append("    overlap=false;")
    dot_code.append("    splines=true;")
    dot_code.append("    node [shape=box, style=\"rounded,filled\", fontsize=10];")
    dot_code.append("    edge [fontsize=8];")

    # Mapear alunos para (cor_de_fundo, cor_da_fonte)
    student_to_style = {}
    
    # NOVA LISTA DE CORES: Uma lista maior de cores pastel seguras
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
        font_color = "black" # Padrão
        
        if i < len(colors):
            group_color = colors[i]
        else:
            # Se mais grupos que cores pré-definidas, gera uma cor aleatória
            group_color = generate_random_color(group[0]) 
            
            # --- A LÓGICA DE CORREÇÃO ---
            # Se a cor for escura (luminância < 45%), usa fonte branca.
            if get_luminance(group_color) < 0.45:
                font_color = "white"
            # --- FIM DA LÓGICA ---
        
        for student in group:
            student_to_style[student] = (group_color, font_color)

    # Adicionar nós com suas cores de grupo e fonte
    for student in G.nodes():
        style = student_to_style.get(student, ("#EEEEEE", "black")) # Padrão cinza
        color = style[0]
        fontcolor = style[1]
        dot_code.append(f"    \"{student}\" [fillcolor=\"{color}\", fontcolor=\"{fontcolor}\"];")
    
    # Adicionar arestas
    for u, v, data in G.edges(data=True):
        edge_color = "gray"
        penwidth = "1.0"
        
        # --- ESTA É A CORREÇÃO ---
        # A variável 'dir_val' agora NÃO contém colchetes.
        dir_val = "dir=none" 
        # --- FIM DA CORREÇÃO ---

        if data['weight'] == 2:
            edge_color = "blue"
            penwidth = "2.5"
        
        if frozenset([u,v]) in forbidden_pairs:
            edge_color = "red"
            penwidth = "3.0"
            dot_code.append(f"    \"{u}\" -> \"{v}\" [color=\"{edge_color}\", penwidth={penwidth}, style=dashed, tooltip=\"Restrição: NÃO pode ficar junto!\", dir=none];")
        else:
            # A linha corrigida agora junta os atributos corretamente
            dot_code.append(f"    \"{u}\" -> \"{v}\" [color=\"{edge_color}\", penwidth={penwidth}, {dir_val}];")

    dot_code.append("}")
    return "\n".join(dot_code)


# --- O Endpoint Principal da API ---

@app.route('/process', methods=['POST'])
def process_csv():
    try:
        # 1. Obter dados do request
        csv_file = request.files['csv_file']
        group_size = int(request.form['group_size'])
        restrictions_text = request.form['restrictions']

        if not csv_file:
            return jsonify({"error": "Nenhum arquivo CSV enviado."}), 400

        # 2. Ler e Processar o CSV
        # Voltamos para UTF-8, pois 'latin-1' estava causando 'AraÃºjo'
        data = io.StringIO(csv_file.stream.read().decode("UTF-8"))
        df = pd.read_csv(data)

        # Encontra colunas dinamicamente
        name_col = None
        for col in df.columns:
            if col.lower() == 'nome' or col.lower() == 'name':
                name_col = col
                break
        if not name_col: 
            name_col = next((col for col in df.columns if 'nome' in col.lower() and 'usuário' not in col.lower()), None)

        option_cols = [col for col in df.columns if 'opção' in col.lower() or 'escreva' in col.lower()]

        if not name_col:
            return jsonify({"error": "Não foi possível encontrar a coluna 'Nome' ou similar."}), 400
        if not option_cols:
            return jsonify({"error": "Não foi possível encontrar colunas de 'opção' ou 'escreva'."}), 400

        # 3. Limpeza e Padronização de Nomes
        voter_names = list(df[name_col].dropna().unique())
        all_choices = []
        for col in option_cols:
            all_choices.extend(list(df[col].dropna().unique()))

        name_map = get_name_map(voter_names, all_choices)
        
        valid_official_names = set(voter_names).union(set(name_map.values()))
        
        votes_map = {}
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

        # 4. Construir Grafo
        official_voter_list = list(votes_map.keys())
        all_students_in_graph = set(official_voter_list)
        for choices in votes_map.values():
            all_students_in_graph.update(choices)

        all_students_in_graph = [s for s in all_students_in_graph if s in valid_official_names]
        G = build_graph(all_students_in_graph, votes_map)
        
        # 5. Processar Restrições
        forbidden_pairs = set()
        for line in restrictions_text.splitlines():
            if line.strip():
                names = [name.strip() for name in line.split(',')]
                if len(names) >= 2:
                    name1_official = name_map.get(names[0])
                    name2_official = name_map.get(names[1])
                    if name1_official and name2_official:
                        forbidden_pairs.add(frozenset([name1_official, name2_official]))
        
        # 6. Algoritmo de Agrupamento
        unassigned_students = set(all_students_in_graph) 
        final_groups = []
        warnings = []

        all_edges = sorted(G.edges(data=True), key=lambda x: x[2]['weight'], reverse=True)
        
        # Fase 1: Formar grupos a partir de pares conectados e preencher
        for u, v, data in all_edges:
            if u in unassigned_students and v in unassigned_students:
                if frozenset([u, v]) not in forbidden_pairs:
                    new_group = [u, v]
                    unassigned_students.remove(u)
                    unassigned_students.remove(v)
                    
                    while len(new_group) < group_size and unassigned_students:
                        best_candidate = None
                        max_affinity = -1
                        
                        possible_candidates = [
                            s for s in unassigned_students 
                            if not is_forbidden(s, new_group, forbidden_pairs)
                        ]
                        
                        for student in possible_candidates:
                            affinity = get_affinity(G, student, new_group)
                            if affinity > max_affinity: 
                                max_affinity = affinity
                                best_candidate = student
                        
                        if best_candidate and max_affinity > 0:
                            new_group.append(best_candidate)
                            unassigned_students.remove(best_candidate)
                        else:
                            break 

                    if len(new_group) >= 2: 
                        final_groups.append(new_group)
                    else: 
                        for member in new_group:
                            unassigned_students.add(member)
        
        # Fase 2: Agrupar alunos "soltos" restantes
        for student in list(unassigned_students): 
            if student not in unassigned_students: 
                 continue
                 
            for group in final_groups:
                if len(group) < group_size and not is_forbidden(student, group, forbidden_pairs):
                    group.append(student)
                    unassigned_students.remove(student)
                    break
        
        while unassigned_students:
            student = unassigned_students.pop()
            new_group = [student]
            
            temp_unassigned = list(unassigned_students)
            for other in temp_unassigned:
                if len(new_group) < group_size:
                    if not is_forbidden(other, new_group, forbidden_pairs):
                        new_group.append(other)
                        unassigned_students.remove(other)
                else:
                    break
            
            final_groups.append(new_group)
            if len(new_group) > 1 and len(new_group) < group_size:
                warnings.append(f"Grupo {len(final_groups)} ({', '.join(new_group)}) foi formado com menos membros ({len(new_group)}) que o desejado ou com alunos sem conexões fortes.")
            elif len(new_group) == 1:
                 warnings.append(f"Grupo {len(final_groups)} ({new_group[0]}) possui apenas 1 membro, pois não foi possível alocá-lo.")

        # 7. Gerar DOT do Grafo
        dot_code = generate_dot_graph(G, final_groups, forbidden_pairs)

        return jsonify({"groups": final_groups, "warnings": warnings, "dot_code": dot_code})

    except Exception as e:
        app.logger.error(f"Erro no processamento: {e}")
        return jsonify({"error": f"Ocorreu um erro interno: {str(e)}"}), 500
