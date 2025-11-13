document.getElementById("download-svg-btn").addEventListener("click", function () {
  const graphContainer = document.getElementById("graph-container");
  const svgElement = graphContainer.querySelector("svg");

  if (!svgElement) {
    alert("Erro: Não foi possível encontrar o grafo SVG para baixar.");
    return;
  }

  const svgData = new XMLSerializer().serializeToString(svgElement);
  const blob = new Blob([svgData], { type: "image/svg+xml;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "grafo_grupos.svg";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(link.href);
});

document.getElementById("group-form").addEventListener("submit", async function (e) {
  e.preventDefault();

  const csvFile = document.getElementById("csv_file").files[0];
  const warningsContainer = document.getElementById("warnings-container");
  const resultsArea = document.getElementById("results-area");

  if (!csvFile) {
    document.getElementById("groups-container").innerHTML = "";
    document.getElementById("graph-container").innerHTML =
      '<p class="graph-placeholder">O grafo será renderizado aqui.</p>';
    document.getElementById("graph-download-buttons").classList.add("hidden");

    let errorMsg = `<strong>Erro: Nenhum arquivo CSV foi selecionado.</strong> Por favor, anexe o arquivo de votos.
                       <br><br>
                       O cabeçalho do CSV deve conter:
                       <ul>
                           <li>Uma coluna com <code>Nome</code>.</li>
                           <li>Uma ou mais colunas de <code>opção</code> (ex: 'Escreva o nome da sua primeira opção...').</li>
                           <li>(Opcional) Uma coluna <code>Gênero</code> (com 'Masculino'/'Feminino') se for balancear.</li>
                       </ul>`;

    warningsContainer.innerHTML = `<div class="error-box">${errorMsg}</div>`;
    resultsArea.classList.remove("hidden");
    return;
  }

  const form = e.target;
  const groupSize = document.getElementById("group_size").value;
  const restrictions = document.getElementById("restrictions").value;
  const balanceGender = document.getElementById("balance_gender").checked;

  const loadingEl = document.getElementById("loading");
  const groupsContainer = document.getElementById("groups-container");
  const graphContainer = document.getElementById("graph-container");
  const calculateBtn = document.getElementById("calculate-btn");
  const graphDownloadButtons = document.getElementById("graph-download-buttons");

  // Resetar UI
  loadingEl.classList.remove("hidden");
  resultsArea.classList.add("hidden");
  warningsContainer.innerHTML = "";
  groupsContainer.innerHTML = "";
  graphContainer.innerHTML =
    '<p class="graph-placeholder">O grafo será renderizado aqui. Pode demorar um pouco em bases de dados grandes.</p>';
  graphDownloadButtons.classList.add("hidden");
  calculateBtn.disabled = true;

  // Criar FormData para enviar
  const formData = new FormData();
  formData.append("csv_file", csvFile);
  formData.append("group_size", groupSize);
  formData.append("restrictions", restrictions);
  formData.append("balance_gender", balanceGender);

  try {
    const response = await fetch("/process", {
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
      graphContainer.innerHTML = "";
      try {
        const viz = new Viz();
        const svg = await viz.renderString(data.dot_code);
        graphContainer.innerHTML = svg;
        graphDownloadButtons.classList.remove("hidden");
      } catch (vizError) {
        graphContainer.innerHTML = `<p style="color: red;">Erro ao renderizar o grafo: ${vizError.message}</p>`;
        console.error("Erro ao renderizar Viz.js:", vizError);
      }
    }

    resultsArea.classList.remove("hidden");
  } catch (error) {
    console.error("Erro ao calcular grupos:", error);
    resultsArea.classList.remove("hidden");
    warningsContainer.innerHTML = `<p style="background-color: #fbe5e5; border-color: #e74c3c; color: #c0392b;">Erro: ${error.message}</p>`;
  } finally {
    loadingEl.classList.add("hidden");
    calculateBtn.disabled = false;
  }
});
