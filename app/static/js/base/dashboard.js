let graficoDia;
let graficoPagamento;

const verRankingCompleto = document.getElementById('verRankingCompleto')

async function carregarRelatorio() {
    const vendedor = document.getElementById("filtroVendedor").value;

    const resp = await fetch(`/api/relatorios?vendedor=${vendedor}`);
    const data = await resp.json();

    // Atualiza os cards
    document.getElementById("cardTotalVendas").innerText = data.total_vendas;
    document.getElementById("cardValorTotal").innerText = "R$ " + data.total_valor.toLocaleString("pt-BR", { minimumFractionDigits: 2 });
    document.getElementById("cardPagos").innerText = data.pagos;
    document.getElementById("cardPendentes").innerText = data.pendentes;
    document.getElementById("cardEntregues").innerText = data.total_entregues;
    // Gráfico: vendas por dia
    if (graficoDia) graficoDia.destroy();

    graficoDia = new Chart(document.getElementById("graficoVendasDia"), {
        type: "bar",
        data: {
            labels: data.vendas_dia_labels,
            datasets: [{
                label: "Vendas",
                data: data.vendas_dia_valores,
                backgroundColor: "#f6a50e",
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, ticks: { precision: 0 } }
            }
        }
    });

    // Gráfico: status de pagamento
    if (graficoPagamento) graficoPagamento.destroy();

    graficoPagamento = new Chart(document.getElementById("graficoPagamento"), {
        type: "doughnut",
        data: {
            labels: ["Pagos", "Pendentes"],
            datasets: [{
                data: [data.pagos, data.pendentes],
                backgroundColor: ["#16a34a", "#ef4444"]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: "bottom", labels: { boxWidth: 12, padding: 16 } }
            }
        }
    });

    // Ranking top 3
    const ranking = document.getElementById("rankingVendedores");
    ranking.innerHTML = "";

    data.ranking.slice(0, 3).forEach((v, i) => {
        const medalha = i === 0 ? "🥇" : i === 1 ? "🥈" : "🥉";

        ranking.innerHTML += `
<div class="flex justify-between items-center bg-slate-50 dark:bg-slate-700 p-3 rounded-lg animate-fadeIn">
    <div class="flex items-center gap-3">
        <span class="text-primary font-bold text-lg">${medalha}</span>
        <span class="font-semibold">${v.nome}</span>
    </div>
    <span class="text-sm font-bold">${v.total} vendas</span>
</div>
`;
    });

    // Se tiver mais de 3, botão para ver completo
    if (data.ranking.length > 3) {
        ranking.innerHTML += `
<button id="verRankingCompleto" class="mt-3 w-full py-2 rounded-xl border border-primary text-primary font-bold hover:bg-primary/5 transition">
    Ver Ranking Completo
</button>`;
    }

    document.getElementById('verRankingCompleto').addEventListener('click', () => {
        window.location.href = '/ranking';
    });


    // Exportar PDF
    document.getElementById("exportarPDF").addEventListener("click", () => {
        window.print();
    });

    // Exportar Excel
    document.getElementById("exportarExcel").addEventListener("click", () => {
        const vendedor = document.getElementById("filtroVendedor").value
        window.open(`/relatorios/exportar/excel?vendedor=${vendedor}`, "_blank")
    })

}

// Filtro
document.getElementById("filtroVendedor").addEventListener("input", () => carregarRelatorio());




// Inicializa
carregarRelatorio();