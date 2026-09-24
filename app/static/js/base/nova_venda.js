document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("form-nova-venda");
    const rows = document.getElementById("linhas-itens");
    const total = document.getElementById("total-venda");
    const error = document.getElementById("itens-erro");
    const payload = document.getElementById("items-payload");
    const legacyProduct = document.getElementById("produto_id_legado");
    const legacyQuantity = document.getElementById("quantidade_legada");
    const money = value => `R$ ${value.toFixed(2).replace(".", ",")}`;
    const showError = message => { error.textContent = message; error.classList.toggle("hidden", !message); };

    function selectedIds() {
        return [...rows.querySelectorAll(".item-produto")].map(select => select.value).filter(Boolean);
    }

    function refresh() {
        const selected = selectedIds();
        let sum = 0;
        let valid = rows.children.length > 0;
        const seen = new Set();
        rows.querySelectorAll(".item-venda").forEach(row => {
            const select = row.querySelector(".item-produto");
            const quantity = row.querySelector(".item-quantidade");
            const id = select.value;
            const amount = Number(quantity.value);
            const duplicate = id && seen.has(id);
            const lineValid = id && Number.isInteger(amount) && amount > 0 && !duplicate;
            if (id) seen.add(id);
            valid = valid && Boolean(lineValid);
            select.classList.toggle("border-red-500", Boolean(duplicate));
            quantity.classList.toggle("border-red-500", !(Number.isInteger(amount) && amount > 0));
            const price = Number(select.selectedOptions[0]?.dataset.preco || 0);
            const subtotal = lineValid ? price * amount : 0;
            row.querySelector(".item-subtotal").textContent = money(subtotal);
            sum += subtotal;
            [...select.options].forEach(option => {
                option.hidden = Boolean(option.value && selected.includes(option.value) && option.value !== id);
            });
        });
        total.textContent = money(sum);
        return valid;
    }

    function addRow() {
        const firstSelect = rows.querySelector(".item-produto");
        const row = document.createElement("div");
        row.className = "item-venda rounded-xl bg-surface dark:bg-slate-800 p-3 shadow-sm space-y-2";
        row.innerHTML = `<div class="flex gap-2 items-start"><select class="item-produto flex-1 min-h-14 rounded-xl border-slate-200 bg-surface" required><option value="">Selecione o produto</option></select><button type="button" class="remover-item min-h-14 min-w-14 rounded-xl bg-red-50 text-red-600 font-bold" aria-label="Remover produto">×</button></div><div class="flex items-center gap-3"><label class="text-sm font-semibold">Quantidade</label><input class="item-quantidade min-h-12 w-24 rounded-xl border-slate-200" type="number" min="1" step="1" value="1" required><span class="item-subtotal ml-auto font-bold">R$ 0,00</span></div>`;
        [...firstSelect.options].forEach(option => { if (option.value) row.querySelector("select").appendChild(option.cloneNode(true)); });
        rows.appendChild(row);
        refresh();
        row.querySelector(".item-produto").focus();
    }

    document.getElementById("adicionar-item").addEventListener("click", addRow);
    rows.addEventListener("click", event => {
        const button = event.target.closest(".remover-item");
        if (!button) return;
        button.closest(".item-venda").remove();
        refresh();
    });
    rows.addEventListener("input", () => { showError(""); refresh(); });
    rows.addEventListener("change", () => { showError(""); refresh(); });

    const initial = JSON.parse(rows.dataset.items || "[]");
    rows.querySelectorAll(".item-produto").forEach((select, index) => { if (initial[index]) select.value = String(initial[index]); });
    refresh();
    document.getElementById("pagar-total").addEventListener("click", () => {
        document.getElementById("forma_pagamento").value = "pix";
        const amount = [...rows.querySelectorAll(".item-subtotal")]
            .reduce((sum, item) => sum + Number(item.textContent.replace("R$ ", "").replace(".", "").replace(",", ".")), 0);
        document.getElementById("pagamento_valor").value = amount.toFixed(2);
    });

    form.addEventListener("submit", async event => {
        event.preventDefault();
        const items = [];
        const seen = new Set();
        rows.querySelectorAll(".item-venda").forEach(row => {
            const productId = row.querySelector(".item-produto").value;
            const quantity = Number(row.querySelector(".item-quantidade").value);
            if (productId && Number.isInteger(quantity) && quantity > 0 && !seen.has(productId)) {
                seen.add(productId);
                items.push({ produto_id: Number(productId), quantidade: quantity });
            }
        });
        if (!items.length || items.length !== rows.querySelectorAll(".item-venda").length) {
            showError("Informe um produto diferente e uma quantidade inteira maior que zero em cada linha.");
            return;
        }
        payload.value = JSON.stringify(items);
        legacyProduct.value = items[0].produto_id;
        legacyQuantity.value = items[0].quantidade;
        try {
            const response = await fetch(form.action, { method: "POST", body: new FormData(form) });
            if (!response.ok) throw new Error("request failed");
            await Swal.fire({ icon: "success", title: form.dataset.vendaId ? "Venda atualizada!" : "Venda registrada!", showConfirmButton: false, timer: 1500 });
            if (!form.dataset.vendaId) window.location.reload();
        } catch (_) {
            showError("Não foi possível salvar a venda. Verifique os dados e tente novamente.");
        }
    });

    const sellerInput = document.getElementById("vendedor_search");
    const sellerId = document.getElementById("vendedor_id");
    const sellerResults = document.getElementById("vendedor_resultados");
    if (sellerInput) {
        let timer;
        sellerInput.addEventListener("input", () => {
            sellerId.value = "";
            clearTimeout(timer);
            const query = sellerInput.value.trim();
            if (query.length < 2) { sellerResults.classList.add("hidden"); return; }
            timer = setTimeout(async () => {
                const response = await fetch(`/buscar-vendedores?q=${encodeURIComponent(query)}`);
                const sellers = await response.json();
                sellerResults.innerHTML = "";
                sellers.forEach(seller => {
                    const option = document.createElement("button");
                    option.type = "button";
                    option.className = "block w-full text-left px-4 py-3";
                    option.textContent = seller.nome;
                    option.onclick = () => { sellerInput.value = seller.nome; sellerId.value = seller.id; sellerResults.classList.add("hidden"); };
                    sellerResults.appendChild(option);
                });
                sellerResults.classList.toggle("hidden", sellers.length === 0);
            }, 250);
        });
    }
    document.getElementById("retorno").addEventListener("click", () => { window.location.href = "/gestao-vendas"; });
});
