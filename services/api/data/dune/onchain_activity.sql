-- ============================================================================
-- DeFiScope AI - on-chain activity (one saved Dune query, four metrics)
-- ============================================================================
-- Paste this into Dune, save it, and put the numeric query id in
-- DEFISCOPE_DUNE_ACTIVITY_QUERY_ID. The backend passes three parameters on
-- every execution; declare them in the Dune query editor with these TYPES:
--
--   chain      Text                e.g. ethereum, arbitrum, bsc
--                                 Injected verbatim (it selects the catalog),
--                                 which is why it must come from the curated
--                                 mapping file, never from user input.
--   addresses  Array<Varbinary>    the protocol's core contracts, 0x-prefixed
--   days       Integer             lookback window (DEFISCOPE_DUNE_LOOKBACK_DAYS)
--
-- Output contract - the backend decodes exactly these column names
-- (app/clients/dune.py::DuneActivityRow). A renamed or dropped column degrades
-- to a NULL metric plus a log line, never to zero:
--
--   day                date      UTC day
--   active_wallets     bigint    distinct senders with >=1 successful tx
--   tx_count           bigint    successful txs to the tracked contracts
--   tx_volume_usd      double    USD value of token transfers INTO the contracts
--   returning_wallets  bigint    of today's wallets, those also seen in the
--                                previous 30 days
--
-- Definitions and their limits are documented in docs/methodology.md. Both
-- matter: these measure *contract-level activity*, not users. A router or
-- wrapper inflates tx_count without meaning more users, and tx_volume_usd
-- counts inflows only, so a swap's two legs are not both counted.
--
-- NOT executed against Dune in this session (no API key available), so the
-- table/column names below have not been validated live. Validate with one
-- manual run in the Dune UI before wiring the id into the backend.
-- ============================================================================

with tx as (
    select
        date_trunc('day', block_time) as day,
        "from"                        as wallet,
        count(*)                      as tx_count
    from {{chain}}.transactions
    where block_time >= date_trunc('day', now()) - interval '{{days}}' day
      -- Complete days only: an in-progress day would plot a partial bar that
      -- looks like a collapse.
      and block_time < date_trunc('day', now())
      and success
      and contains({{addresses}}, "to")
    group by 1, 2
),

daily as (
    select
        day,
        count(distinct wallet) as active_wallets,
        sum(tx_count)          as tx_count
    from tx
    group by 1
),

returning as (
    select
        today.day,
        count(distinct today.wallet) as returning_wallets
    from tx as today
    where exists (
        select 1
        from tx as prior
        where prior.wallet = today.wallet
          and prior.day < today.day
          and prior.day >= today.day - interval '30' day
    )
    group by 1
),

inflow as (
    select
        date_trunc('day', block_time) as day,
        sum(amount_usd)               as tx_volume_usd
    from tokens_{{chain}}.transfers
    where block_time >= date_trunc('day', now()) - interval '{{days}}' day
      and block_time < date_trunc('day', now())
      and contains({{addresses}}, "to")
    group by 1
)

select
    d.day,
    d.active_wallets,
    d.tx_count,
    i.tx_volume_usd,
    coalesce(r.returning_wallets, 0) as returning_wallets
from daily as d
left join returning as r on r.day = d.day
left join inflow    as i on i.day = d.day
order by d.day desc
