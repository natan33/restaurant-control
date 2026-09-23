const vendasLista = document.getElementById("vendas_lista");
const searchInput = document.querySelector('input[placeholder*="Pesquisar vendas"]');
const filtros = document.querySelectorAll("header button"); // seus botões de filtro

let offset = 0;
const limit = 5; // quantas vendas carregar por vez
let loading = false;
let hasMore = true;
let currentQuery = "";
let currentFiltro = "";

// Carrega vendas via fetch
async function carregarVendas(query = "", filtro = "", reset = false) {
    if (loading || !hasMore) return;
    loading = true;

    if (reset) {
        vendasLista.innerHTML = "";
        offset = 0;
        hasMore = true;
    }

    let url = `/api/vendas?q=${encodeURIComponent(query)}&limit=${limit}&offset=${offset}`;
    if (filtro) url += `&filtro=${encodeURIComponent(filtro)}`;


    const res = await fetch(url);
    const vendas = await res.json();

    //vendasLista.innerHTML = "";

    if (vendas.length < limit) hasMore = false; // não há mais registros
    offset += vendas.length;

    vendas.forEach(v => {
        const card = document.createElement("div");
        card.className = "bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm border border-primary/5 flex flex-col gap-3";
        card.dataset.vendaId = v.id;

        card.innerHTML = `
<div class="flex justify-between items-start gap-4">
    <div class="flex flex-col gap-1">
        <p class="text-xs text-slate-400 font-mono">#VND-${v.id.toString().padStart(6, '0')}</p>
        <h4 class="text-secondary dark:text-slate-100 font-bold text-base">${v.produto}</h4>
        <p class="text-sm text-slate-500">Vendedor: ${v.vendedor}</p>
        <p class="text-sm text-slate-500">Cliente: ${v.comprador_nome}</p>
    </div>

    <div class="flex flex-col gap-2 items-end">
        <!-- Badge de status de entrega -->
        <span class="px-2 py-1 rounded-full entrega-status ${v.status_entrega === 'Entregue' ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400' : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'} text-[10px] font-bold uppercase">
            Entregue: ${v.status_entrega === 'Entregue' ? 'Sim' : 'Não'}
        </span>

        <!-- Badge de status de pagamento -->
        <span class="px-2 py-1 rounded-full pagamento-status ${v.status_pagamento === 'Pago' ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400' : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'} text-[10px] font-bold uppercase">
            Pago: ${v.status_pagamento}
        </span>
    </div>
</div>

<div class="flex justify-between items-center pt-2 border-t border-slate-50 dark:border-slate-700 mt-2">
    <span class="text-primary font-black text-lg">R$ ${v.valor_total.toFixed(2).replace('.', ',')}</span>
    <div class="flex gap-2 items-center">
        <button class="editar size-8 rounded-lg bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 flex items-center justify-center hover:bg-slate-200 dark:hover:bg-slate-600 transition">
            <span class="material-symbols-outlined text-sm">edit</span>
        </button>
        <button class="deletar size-8 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-500 flex items-center justify-center hover:bg-red-100 dark:hover:bg-red-800 transition">
            <span class="material-symbols-outlined text-sm">delete</span>
        </button>
        <!-- Botão apenas com ícone, sem texto duplicado -->
        <button class="entrega size-8 rounded-lg bg-blue-50 dark:bg-blue-900/20 text-blue-500 flex items-center justify-center hover:bg-blue-100 dark:hover:bg-blue-800 transition">
            <span class="material-symbols-outlined text-sm">${v.status_entrega === "Entregue" ? "check_circle" : "inventory"}</span>
        </button>
        <button class="pagamento size-8 rounded-lg bg-green-50 dark:bg-green-900/20 text-green-600 flex items-center justify-center hover:bg-green-100 dark:hover:bg-green-800 transition">
            <span class="material-symbols-outlined text-sm">payments</span>
        </button>
    </div>
</div>
`;

        vendasLista.appendChild(card);
    });
    loading = false;
}

window.addEventListener("scroll", () => {
    if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 200) {
        carregarVendas(currentQuery, currentFiltro); // carrega mais quando chegar perto do final
    }
});

// Atualiza resumo
async function carregarResumo() {
    const res = await fetch("/api/cards/gestao");
    const data = await res.json();

    document.getElementById("total-vendas").textContent = data.total;
    document.getElementById("pagos-vendas").textContent = data.pago;
    document.getElementById("pendentes-vendas").textContent = data.pendente;
    document.getElementById("entregues-vendas").textContent = data.pendentes_entrega;
}

// Filtrar via search input
searchInput.addEventListener("input", () => {
    carregarVendas(searchInput.value);
});

// Filtrar via filtros horizontais
filtros.forEach(btn => {
    btn.addEventListener("click", () => {
        const filtro = btn.querySelector("span").textContent.trim();
        carregarVendas(searchInput.value, filtro);
    });
});

// Clique em cards (editar / deletar)
vendasLista.addEventListener("click", async (e) => {
    const card = e.target.closest("[data-venda-id]");
    if (!card) return;
    const vendaId = card.dataset.vendaId;

    if (e.target.closest(".editar")) {
        window.location.href = `/editar-venda/${vendaId}`;
        return;
    }

    if (e.target.closest(".deletar")) {
        const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

        const result = await Swal.fire({
            title: "Excluir venda?",
            text: "Essa ação não pode ser desfeita.",
            icon: "warning",
            showCancelButton: true,
            confirmButtonColor: "#ef4444",
            cancelButtonColor: "#64748b",
            confirmButtonText: "Sim, excluir",
            cancelButtonText: "Cancelar"
        });

        if (!result.isConfirmed) return;

        Swal.fire({
            title: "Excluindo...",
            allowOutsideClick: false,
            didOpen: () => Swal.showLoading()
        });

        try {
            const res = await fetch(`/api/vendas/${vendaId}`, {
                method: "DELETE",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken
                }
            });

            if (res.ok) {
                card.remove();
                carregarResumo();

                Swal.fire({
                    icon: "success",
                    title: "Venda excluída",
                    showConfirmButton: false,
                    timer: 1500
                });
            } else {
                Swal.fire({
                    icon: "error",
                    title: "Erro ao excluir",
                    text: "Não foi possível excluir a venda."
                });
            }
        } catch (error) {
            Swal.fire({
                icon: "error",
                title: "Erro de conexão",
                text: "Falha ao comunicar com o servidor."
            });
        }
    }
});

// =====================
// Filtros e busca
// =====================
searchInput.addEventListener("input", () => {
    currentQuery = searchInput.value;
    currentFiltro = ""; // limpa filtro
    offset = 0;
    hasMore = true;
    carregarVendas(currentQuery, currentFiltro, true);
});

filtros.forEach(btn => {
    btn.addEventListener("click", () => {
        currentFiltro = btn.querySelector("span").textContent.trim();
        currentQuery = searchInput.value;
        offset = 0;
        hasMore = true;
        carregarVendas(currentQuery, currentFiltro, true);
    });
});


// Inicial
document.addEventListener("DOMContentLoaded", () => {
    carregarVendas();
    carregarResumo();
    const verTudoBtn = document.getElementById("ver-tudo");

    verTudoBtn.addEventListener("click", () => {
        // Limpa filtros e pesquisa
        currentQuery = "";
        currentFiltro = "";
        offset = 0;
        hasMore = true;

        // Limpa a lista de vendas antes de recarregar
        vendasLista.innerHTML = "";

        // Recarrega todas as vendas
        carregarVendas();
    });


    const totalCard = document.getElementById("total-vendas");
    const pagosCard = document.getElementById("pagos-vendas");
    const pendentesCard = document.getElementById("pendentes-vendas");
    const entregueCard = document.getElementById("entregues-vendas");
    const searchInput = document.querySelector('input[placeholder*="Pesquisar vendas"]');

    // Função para recarregar vendas com filtro de status
    function filtrarPorStatus(status) {
        currentQuery = status;          // valor que o backend vai filtrar
        currentFiltro = "status pagamento"; // filtro que o backend espera
        offset = 0;                     // reinicia scroll infinito
        hasMore = true;                 // ainda pode carregar mais
        vendasLista.innerHTML = "";     // limpa lista antes de recarregar
        carregarVendas(currentQuery, currentFiltro, true);
    }

    function filtrarPorEntrega(en) {
        currentQuery = '2';                   // Valor fixo '2' conforme seu requisito
        currentFiltro = "Status Entrega";// filtro que o backend espera
        offset = 0;                     // reinicia scroll infinito
        hasMore = true;                 // ainda pode carregar mais
        vendasLista.innerHTML = "";     // limpa lista antes de recarregar
        carregarVendas(currentQuery, currentFiltro, true);
    }

    // Eventos de clique nos cards
    pagosCard.addEventListener("click", () => filtrarPorStatus("Pago"));
    pendentesCard.addEventListener("click", () => filtrarPorStatus("Pendente"));
    entregueCard.addEventListener("click", () => filtrarPorEntrega("Entrega"));
    totalCard.addEventListener("click", () => carregarVendas()); // total limpa filtros


    const btnExportar = document.getElementById("btn-exportar");

    btnExportar.addEventListener("click", () => {
        let url = `/exportar-vendas`;

        if (currentQuery) url += `?q=${encodeURIComponent(currentQuery)}`;
        if (currentFiltro) url += currentQuery ? `&filtro=${encodeURIComponent(currentFiltro)}` : `?filtro=${encodeURIComponent(currentFiltro)}`;

        window.location.href = url;
    });


    vendasLista.addEventListener("click", async (e) => {
        const card = e.target.closest("[data-venda-id]");
        if (!card) return;
        const vendaId = card.dataset.vendaId;

        // EDITAR
        if (e.target.closest(".editar")) {
            window.location.href = `/editar-venda/${vendaId}`;
            return;
        }

        // EXCLUIR
        if (e.target.closest(".deletar")) {
            // ... seu código existente de Swal.fire excluir ...
            return;
        }


        // TOGGLE PAGAMENTO
        if (e.target.closest(".pagamento")) {
            const statusSpan = card.querySelector("span.pagamento-status");
            // Extrai apenas o valor após "Pago: " ou verifica o texto
            const statusAtual = statusSpan.textContent.includes("Pago") && !statusSpan.textContent.includes("Pendente") ? "Pago" : "Pendente";

            const confirmMsg = statusAtual === "Pendente"
                ? "Confirmar pagamento desta venda?"
                : "Deseja alterar o status para Pendente?";

            const result = await Swal.fire({
                title: confirmMsg,
                icon: "warning",
                showCancelButton: true,
                confirmButtonColor: "#10b981", // Verde
                cancelButtonColor: "#64748b",
                confirmButtonText: "Sim",
                cancelButtonText: "Cancelar"
            });

            if (!result.isConfirmed) return;

            Swal.fire({
                title: "Atualizando pagamento...",
                allowOutsideClick: false,
                didOpen: () => Swal.showLoading()
            });

            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

                const res = await fetch(`/api/vendas/${vendaId}/status/pagamento`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken
                    }
                });

                const data = await res.json();

                if (res.ok) {
                    // Atualiza badge visual do card
                    statusSpan.textContent = `Pago: ${data.status_pagamento}`;

                    if (data.status_pagamento === "Pago") {
                        statusSpan.classList.remove("bg-red-100", "dark:bg-red-900/30", "text-red-700", "dark:text-red-400");
                        statusSpan.classList.add("bg-green-100", "dark:bg-green-900/30", "text-green-700", "dark:text-green-400");
                    } else {
                        statusSpan.classList.remove("bg-green-100", "dark:bg-green-900/30", "text-green-700", "dark:text-green-400");
                        statusSpan.classList.add("bg-red-100", "dark:bg-red-900/30", "text-red-700", "dark:text-red-400");
                    }

                    Swal.fire({
                        icon: "success",
                        title: "Status de pagamento atualizado!",
                        showConfirmButton: false,
                        timer: 1500
                    });

                    carregarResumo(); // Atualiza os números nos cards do topo
                } else {
                    throw new Error();
                }
            } catch (err) {
                Swal.fire({
                    icon: "error",
                    title: "Erro",
                    text: "Não foi possível atualizar o pagamento."
                });
            }
        }

        // TOGGLE ENTREGA
        if (e.target.closest(".entrega")) {
            const statusSpan = card.querySelector("span.entrega-status"); // <-- agora usamos uma classe específica
            const statusAtual = statusSpan.textContent === "Entregue" ? "Entregue" : "Pendente";

            const confirmMsg = statusAtual === "Pendente"
                ? "Deseja marcar esta venda como entregue?"
                : "Deseja desmarcar a entrega desta venda?";

            const result = await Swal.fire({
                title: confirmMsg,
                icon: "question",
                showCancelButton: true,
                confirmButtonColor: "#3b82f6",
                cancelButtonColor: "#64748b",
                confirmButtonText: "Sim",
                cancelButtonText: "Cancelar"
            });

            if (!result.isConfirmed) return;

            Swal.fire({
                title: statusAtual === "Pendente" ? "Marcando como entregue..." : "Desmarcando entrega...",
                allowOutsideClick: false,
                didOpen: () => Swal.showLoading()
            });

            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

                const res = await fetch(`/api/vendas/${vendaId}/entrega`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken
                    }
                });

                const data = await res.json();

                if (res.ok) {
                    // Atualiza badge visual do card
                    if (data.status_entrega === "Entregue") {
                        statusSpan.textContent = "Entregue";
                        statusSpan.classList.remove("bg-red-100", "dark:bg-red-900/30", "text-red-700", "dark:text-red-400");
                        statusSpan.classList.add("bg-green-100", "dark:bg-green-900/30", "text-green-700", "dark:text-green-400");
                    } else {
                        statusSpan.textContent = "Pendente";
                        statusSpan.classList.remove("bg-green-100", "dark:bg-green-900/30", "text-green-700", "dark:text-green-400");
                        statusSpan.classList.add("bg-red-100", "dark:bg-red-900/30", "text-red-700", "dark:text-red-400");
                    }

                    Swal.fire({
                        icon: "success",
                        title: `Entrega ${data.status_entrega === "Entregue" ? "marcada" : "desmarcada"} com sucesso`,
                        showConfirmButton: false,
                        timer: 1500
                    });

                    carregarResumo();
                } else {
                    Swal.fire({
                        icon: "error",
                        title: "Erro",
                        text: data.error || "Não foi possível atualizar a entrega"
                    });
                }
            } catch (err) {
                Swal.fire({
                    icon: "error",
                    title: "Erro de conexão",
                    text: "Falha ao comunicar com o servidor."
                });
            }
        }
    });

    // Seleciona o botão de voltar
    const botaoVoltar = document.getElementById('retorno')

    // Se não funcionar com :contains(), podemos usar o querySelector apenas pelo botão no header

    botaoVoltar.addEventListener('click', () => {
        // Redireciona para a tela de gestão de vendas
        window.location.href = '/portal';
    });
});