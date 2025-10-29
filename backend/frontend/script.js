// --- NOVO: LÓGICA DE DOWNLOAD DO SVG ---
// Esta função é adicionada no topo e será "ligada" ao botão
document.getElementById("download-svg-btn").addEventListener("click", function () {
  const graphContainer = document.getElementById("graph-container");
  const svgElement = graphContainer.querySelector("svg");

  if (!svgElement) {
    alert("Erro: Não foi possível encontrar o grafo SVG para baixar.");
    return;
  }

  // 1. Pega o conteúdo do SVG como texto
  const svgData = new XMLSerializer().serializeToString(svgElement);

  // 2. Cria um "Blob", que é um objeto de arquivo em memória
  const blob = new Blob([svgData], { type: "image/svg+xml;charset=utf-8" });

  // 3. Cria um link <a> invisível para disparar o download
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "grafo_grupos.svg"; // Nome do arquivo

  // 4. Adiciona ao corpo, clica, e remove
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  // 5. Limpa o objeto da memória
  URL.revokeObjectURL(link.href);
});
// --- FIM DA NOVA LÓGICA ---

// --- FUNÇÃO DE SUBMIT (COM PEQUENAS MUDANÇAS) ---
document.getElementById("group-form").addEventListener("submit", async function (e) {
  e.preventDefault();

  const form = e.target;
  const csvFile = document.getElementById("csv_file").files[0];
  const groupSize = document.getElementById("group_size").value;
  const restrictions = document.getElementById("restrictions").value;

  const loadingEl = document.getElementById("loading");
  const resultsArea = document.getElementById("results-area");
  const warningsContainer = document.getElementById("warnings-container");
  const groupsContainer = document.getElementById("groups-container");
  const graphContainer = document.getElementById("graph-container");
  const calculateBtn = document.getElementById("calculate-btn");
  const graphDownloadButtons = document.getElementById("graph-download-buttons"); // Novo!

  // Resetar UI
  loadingEl.classList.remove("hidden");
  resultsArea.classList.add("hidden");
  warningsContainer.innerHTML = "";
  groupsContainer.innerHTML = "";
  graphContainer.innerHTML =
    '<p class="graph-placeholder">O grafo será renderizado aqui. Pode demorar um pouco em bases de dados grandes.</p>';
  graphDownloadButtons.classList.add("hidden"); // Esconde o botão de download
  calculateBtn.disabled = true;

  // Criar FormData para enviar
  const formData = new FormData();
  formData.append("csv_file", csvFile);
  formData.append("group_size", groupSize);
  formData.append("restrictions", restrictions);

  try {
    const response = await fetch("/process", {
      // Porta 5003
      method: "POST",
      body: formData,
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Erro desconhecido no servidor.");
    }

    // 1. Exibir Avisos (Warnings)
    if (data.warnings && data.warnings.length > 0) {
      data.warnings.forEach((warning) => {
        const p = document.createElement("p");
        p.textContent = `Aviso: ${warning}`;
        warningsContainer.appendChild(p);
      });
    }

    // 2. Exibir Grupos
    if (data.groups && data.groups.length > 0) {
      data.groups.forEach((group, index) => {
        const groupCard = document.createElement("div");
        groupCard.className = "group-card";

        const title = document.createElement("h3");
        title.textContent = `Grupo ${index + 1}`;
        groupCard.appendChild(title);

        const list = document.createElement("ul");
        group.forEach((member) => {
          const li = document.createElement("li");
          li.textContent = member;
          list.appendChild(li);
        });
        groupCard.appendChild(list);
        groupsContainer.appendChild(groupCard);
      });
    }

    // 3. Renderizar o Grafo
    if (data.dot_code) {
      graphContainer.innerHTML = ""; // Limpa o placeholder
      try {
        const viz = new Viz();
        const svg = await viz.renderString(data.dot_code);
        graphContainer.innerHTML = svg;

        // NOVO: Mostra o botão de download APÓS o grafo ser renderizado
        graphDownloadButtons.classList.remove("hidden");
      } catch (vizError) {
        graphContainer.innerHTML = `<p style="color: red;">Erro ao renderizar o grafo: ${vizError.message}</p>`;
        console.error("Erro ao renderizar Viz.js:", vizError);
      }
    }

    resultsArea.classList.remove("hidden");
  } catch (error) {
    console.error("Erro ao calcular grupos:", error);
    warningsContainer.innerHTML = `<p style="background-color: #fbe5e5; border-color: #e74c3c; color: #c0392b;">Erro: ${error.message}</p>`;
  } finally {
    // Resetar UI
    loadingEl.classList.add("hidden");
    calculateBtn.disabled = false;
  }
});
