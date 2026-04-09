//! Generated Protobuf types from `frontend/src/proto/market.proto`.
//! Built by prost-build in build.rs. Single source of truth shared with the frontend.

pub mod market {
    include!(concat!(env!("OUT_DIR"), "/market.rs"));
}

use crate::events::{FlowEvent, TradeSide};
use prost::Message;

/// Convert a TradeSide enum to the protobuf TradeSide i32.
fn side_to_proto(side: TradeSide) -> i32 {
    match side {
        TradeSide::Unknown => market::TradeSide::SideUnknown as i32,
        TradeSide::Buy => market::TradeSide::SideBuy as i32,
        TradeSide::Sell => market::TradeSide::SideSell as i32,
    }
}

/// Encode a FlowEvent as a protobuf MarketMessage binary.
pub fn encode_flow_event(event: &FlowEvent) -> Vec<u8> {
    let payload = match event {
        FlowEvent::Tick { price, size, side, timestamp } => {
            market::market_message::Payload::Tick(market::Tick {
                price: *price,
                size: *size,
                side: side_to_proto(*side),
                timestamp_ms: timestamp.timestamp_millis(),
            })
        }
        FlowEvent::Cvd { value, delta_1m, delta_5m, timestamp } => {
            market::market_message::Payload::Cvd(market::Cvd {
                value: *value,
                delta_1m: *delta_1m,
                delta_5m: *delta_5m,
                timestamp_ms: timestamp.timestamp_millis(),
            })
        }
        FlowEvent::Footprint { bar_time, levels, total_buy_vol, total_sell_vol } => {
            market::market_message::Payload::Footprint(market::Footprint {
                bar_time: *bar_time,
                levels: levels.iter().map(|l| market::FootprintLevel {
                    price: l.price,
                    bid_vol: l.bid_vol,
                    ask_vol: l.ask_vol,
                }).collect(),
                total_buy_vol: *total_buy_vol,
                total_sell_vol: *total_sell_vol,
            })
        }
        FlowEvent::Sweep { price, size, side, levels_hit, timestamp } => {
            market::market_message::Payload::Sweep(market::Sweep {
                price: *price,
                size: *size,
                side: side_to_proto(*side),
                levels_hit: *levels_hit,
                timestamp_ms: timestamp.timestamp_millis(),
            })
        }
        FlowEvent::Imbalance { price, side, ratio, stacked, timestamp } => {
            market::market_message::Payload::Imbalance(market::Imbalance {
                price: *price,
                side: side_to_proto(*side),
                ratio: *ratio,
                stacked: *stacked,
                timestamp_ms: timestamp.timestamp_millis(),
            })
        }
        FlowEvent::Absorption { price, volume, side, held, timestamp } => {
            market::market_message::Payload::Absorption(market::Absorption {
                price: *price,
                volume: *volume,
                side: side_to_proto(*side),
                held: *held,
                timestamp_ms: timestamp.timestamp_millis(),
            })
        }
        FlowEvent::DeltaFlip { from, to, cvd_at_flip, timestamp } => {
            market::market_message::Payload::DeltaFlip(market::DeltaFlip {
                from: side_to_proto(*from),
                to: side_to_proto(*to),
                cvd_at_flip: *cvd_at_flip,
                timestamp_ms: timestamp.timestamp_millis(),
            })
        }
        FlowEvent::LargeTrade { price, size, side, timestamp } => {
            market::market_message::Payload::LargeTrade(market::LargeTrade {
                price: *price,
                size: *size,
                side: side_to_proto(*side),
                timestamp_ms: timestamp.timestamp_millis(),
            })
        }
        FlowEvent::Heartbeat { timestamp, ticks_processed, last_price, data_source } => {
            market::market_message::Payload::Heartbeat(market::Heartbeat {
                timestamp_ms: timestamp.timestamp_millis(),
                ticks_processed: *ticks_processed,
                last_price: *last_price,
                data_source: data_source.clone().unwrap_or_default(),
            })
        }
    };

    let msg = market::MarketMessage {
        payload: Some(payload),
    };
    msg.encode_to_vec()
}

/// Encode a raw JSON string (from Python /ingest) as an ExternalJson protobuf message.
pub fn encode_external_json(json: &str) -> Vec<u8> {
    let msg = market::MarketMessage {
        payload: Some(market::market_message::Payload::External(
            market::ExternalJson { json: json.to_string() },
        )),
    };
    msg.encode_to_vec()
}
