# Webhook Kiwify e painel

O `painel.html` mostra o faturamento líquido confirmado. Cada pedido pago entra uma vez, pelo `my_commission` em centavos (R$ 6,52 = 652).

## Por que uma venda sobrevive ao reinício

O processo grava os webhooks em `data/vendas_kiwify.jsonl`. No plano gratuito do Render o disco é efêmero: quando o serviço dorme ou reinicia, esse arquivo some e `GET /vendas` volta a `[]`.

As vendas que precisam permanecer ficam em `vendas-historico.json`, no repositório, no mesmo formato de `GET /vendas`.

- O painel junta `/vendas` com `vendas-historico.json` e remove a cópia repetida do mesmo `order_id` + evento. Se as duas fontes tiverem o mesmo evento, fica o registro que traz `my_commission`. A soma continua sendo uma vez por `order_id` pago.
- O servidor também mistura o arquivo em `GET /vendas`. O corte dos últimos 50 eventos vale só para o log volátil; o histórico entra inteiro.

Enquanto o processo está no ar, uma venda nova aparece na hora pelo jsonl. Ela continua depois do reinício quando alguém copia o evento para `vendas-historico.json`.

## Como acrescentar uma venda

1. Copie o objeto do pedido (um item de `GET /vendas`, ou o modelo abaixo).
2. Abra `vendas-historico.json` e coloque o objeto dentro do array.
3. Use o `order_id` da Kiwify. O mesmo pedido não precisa aparecer duas vezes.
4. Para entrar no faturamento, o pedido precisa estar pago (`order_status`: `"paid"` ou `event`: `"order_approved"`) e ter `my_commission` em centavos, em `full_payload.Commissions.my_commission` ou no próprio objeto.
5. Faça commit e push. No próximo deploy, `GET /vendas` passa a incluir o pedido. Se o `painel.html` estiver na mesma pasta que o JSON (GitHub Pages, `python3 -m http.server` ou `GET /painel.html` no webhook), o painel soma o arquivo assim que os dois arquivos estão publicados.

```json
{
  "received_at": "2026-10-25T18:37:00-03:00",
  "event": "order_approved",
  "order_status": "paid",
  "order_id": "cole-o-order-id",
  "order_ref": "referencia",
  "payment_method": "pix",
  "product_name": "Nome do produto",
  "amount": 990,
  "kiwify_fee": 338,
  "my_commission": 652,
  "full_payload": {
    "webhook_event_type": "order_approved",
    "order_status": "paid",
    "order_id": "cole-o-order-id",
    "order_ref": "referencia",
    "payment_method": "pix",
    "approved_date": "2026-10-25 18:37",
    "Product": { "product_name": "Nome do produto" },
    "Commissions": {
      "charge_amount": 990,
      "kiwify_fee": 338,
      "my_commission": 652
    }
  }
}
```

`amount` é o bruto em centavos. `kiwify_fee` é a taxa. `my_commission` é o líquido que o painel soma.

## Rotas

```bash
python3 webhook_kiwify.py
```

- `POST /` recebe o webhook da Kiwify
- `GET /vendas` devolve o jsonl recente mais o histórico
- `GET /vendas-historico.json` devolve o arquivo versionado
- `GET /painel.html` abre o painel
- `GET /status` e `POST /status` seguem iguais para os agentes

`GET /` continua respondendo `Webhook Kiwify receiver online` para o health check.

## Limitações

- O disco do plano gratuito do Render é efêmero. `data/vendas_kiwify.jsonl` e um SQLite no mesmo diretório somem no reinício. O que permanece é `vendas-historico.json`, porque ele volta no próximo deploy.
- Uma venda nova não se grava sozinha no Git. Sem segredo nem serviço pago, alguém cola o evento no JSON e faz o deploy.
- O painel não desconta reembolso. Se um pedido do arquivo for reembolsado, apague ou ajuste esse objeto.
- Abrir `painel.html` direto pelo disco (`file://`) pode impedir o navegador de ler o JSON ao lado. Nesse caso o faturamento vem de `GET /vendas`, que já inclui o arquivo depois do deploy. O painel também tenta `https://webhook-kiwify-u4qe.onrender.com/vendas-historico.json` quando o arquivo local não abre.
