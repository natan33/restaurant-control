
document.addEventListener("DOMContentLoaded", () => {

    const input = document.getElementById("vendedor_search")
    const resultados = document.getElementById("vendedor_resultados")
    const vendedor_id = document.getElementById("vendedor_id")

    let timeout = null

    input.addEventListener("input", function () {

        const query = this.value.trim()

        // sempre limpar id quando digitar
        vendedor_id.value = ""

        clearTimeout(timeout)

        if (query.length < 2) {
            resultados.classList.add("hidden")
            resultados.innerHTML = ""
            return
        }

        timeout = setTimeout(() => {

            fetch(`/buscar-vendedores?q=${encodeURIComponent(query)}`)
                .then(res => res.json())
                .then(data => {

                    resultados.innerHTML = ""

                    if (data.length === 0) {

                        const criar = document.createElement("div")

                        criar.className =
                            "px-4 py-3 cursor-pointer text-primary font-medium hover:bg-slate-100 dark:hover:bg-slate-700"

                        criar.innerText = `Criar vendedor: "${query}"`

                        criar.onclick = () => {

                            input.value = query
                            vendedor_id.value = ""
                            resultados.classList.add("hidden")

                        }

                        resultados.appendChild(criar)
                        resultados.classList.remove("hidden")
                        return
                    }

                    data.forEach(v => {

                        const item = document.createElement("div")

                        item.className =
                            "px-4 py-3 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-700"

                        item.innerText = v.nome

                        item.onclick = () => {

                            input.value = v.nome
                            vendedor_id.value = v.id
                            resultados.classList.add("hidden")

                        }

                        resultados.appendChild(item)

                    })

                    resultados.classList.remove("hidden")

                })

        }, 300)

    })

    // fechar dropdown clicando fora
    document.addEventListener("click", function (e) {

        if (!input.contains(e.target) && !resultados.contains(e.target)) {
            resultados.classList.add("hidden")
        }

    })

    const produtoInput = document.getElementById("produto_search")
    const produtoResultados = document.getElementById("produto_resultados")
    const produtoId = document.getElementById("produto_id")
    const quantidadeInput = document.getElementById("quantidade")
    const totalDisplay = document.querySelector(".w-full.h-14 span.text-xl")

    let produtoTimeout = null
    let precoSelecionado = 0

    function atualizarTotal() {
        const qtd = parseInt(quantidadeInput.value) || 0
        const total = qtd * precoSelecionado
        totalDisplay.innerText = `R$ ${total.toFixed(2).replace('.', ',')}`
    }

    produtoInput.addEventListener("input", function () {
        clearTimeout(produtoTimeout)
        const query = this.value

        if (query.length < 2) {
            produtoResultados.classList.add("hidden")
            return
        }

        produtoTimeout = setTimeout(() => {
            fetch(`/buscar-produtos?q=${encodeURIComponent(query)}`)
                .then(res => res.json())
                .then(data => {
                    produtoResultados.innerHTML = ""

                    if (data.length === 0) {
                        produtoResultados.classList.add("hidden")
                        return
                    }

                    data.forEach(p => {
                        const preco = p.preco !== undefined ? parseFloat(p.preco) : 0;
                        const item = document.createElement("div");
                        item.className = "px-4 py-3 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-700";
                        item.innerText = `${p.nome} - R$ ${preco.toFixed(2).replace('.', ',')}`;

                        item.onclick = () => {
                            produtoInput.value = p.nome;
                            produtoId.value = p.id;
                            precoSelecionado = preco; // atualiza o preço
                            atualizarTotal(); // recalcula o total
                            produtoResultados.classList.add("hidden");
                        }

                        produtoResultados.appendChild(item);
                    });

                    produtoResultados.classList.remove("hidden")
                })
        }, 300)
    })

    quantidadeInput.addEventListener("input", atualizarTotal)


    // Seleciona o botão de voltar
    const botaoVoltar = document.getElementById('retorno')

    // Se não funcionar com :contains(), podemos usar o querySelector apenas pelo botão no header


    botaoVoltar.addEventListener('click', () => {
        // Redireciona para a tela de gestão de vendas
        window.location.href = '/gestao-vendas';
    });


    // ===========================
    // Envio do formulário via JS
    // ===========================
    const formNovaVenda = document.querySelector('form');
    const totalDisplayS = document.querySelector(".w-full.h-14 span.text-xl");

    // Função para resetar o form
    function resetForm() {
        formNovaVenda.reset();
        // reset total
        totalDisplayS.innerText = "R$ 0,00";
        // reset preço selecionado
        precoSelecionado = 0;
        produtoId.value = "";
        vendedor_id.value = "";
        // limpar inputs de busca
        produtoInput.value = "";
        input.value = "";
    }

    const vendaId = formNovaVenda.dataset.vendaId; // string ou vazio

    formNovaVenda.addEventListener('submit', async function (e) {
        e.preventDefault();

        const formData = new FormData(formNovaVenda);
        const actionUrl = formNovaVenda.getAttribute('action');

        try {
            const res = await fetch(actionUrl, {
                method: 'POST',
                body: formData
            });

            if (!res.ok) throw new Error('Erro ao registrar venda');

            Swal.fire({
                icon: 'success',
                title: vendaId ? 'Venda atualizada!' : 'Venda registrada!',
                showConfirmButton: false,
                timer: 2000
            });

            if (!vendaId) resetForm();

        } catch (err) {
            Swal.fire({
                icon: 'error',
                title: 'Erro',
                text: 'Não foi possível registrar a venda'
            });
            console.error(err);
        }
    });


})