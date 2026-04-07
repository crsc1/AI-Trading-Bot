import * as $protobuf from "protobufjs";
import Long = require("long");
/** Namespace market. */
export namespace market {

    /** Properties of a Tick. */
    interface ITick {

        /** Tick price */
        price?: (number|null);

        /** Tick size */
        size?: (number|Long|null);

        /** Tick side */
        side?: (string|null);

        /** Tick timestampMs */
        timestampMs?: (number|Long|null);
    }

    /** Represents a Tick. */
    class Tick implements ITick {

        /**
         * Constructs a new Tick.
         * @param [properties] Properties to set
         */
        constructor(properties?: market.ITick);

        /** Tick price. */
        public price: number;

        /** Tick size. */
        public size: (number|Long);

        /** Tick side. */
        public side: string;

        /** Tick timestampMs. */
        public timestampMs: (number|Long);

        /**
         * Creates a new Tick instance using the specified properties.
         * @param [properties] Properties to set
         * @returns Tick instance
         */
        public static create(properties?: market.ITick): market.Tick;

        /**
         * Encodes the specified Tick message. Does not implicitly {@link market.Tick.verify|verify} messages.
         * @param message Tick message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: market.ITick, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified Tick message, length delimited. Does not implicitly {@link market.Tick.verify|verify} messages.
         * @param message Tick message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: market.ITick, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a Tick message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns Tick
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): market.Tick;

        /**
         * Decodes a Tick message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns Tick
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): market.Tick;

        /**
         * Verifies a Tick message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a Tick message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns Tick
         */
        public static fromObject(object: { [k: string]: any }): market.Tick;

        /**
         * Creates a plain object from a Tick message. Also converts values to other types if specified.
         * @param message Tick
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: market.Tick, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this Tick to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for Tick
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a Candle. */
    interface ICandle {

        /** Candle open */
        open?: (number|null);

        /** Candle high */
        high?: (number|null);

        /** Candle low */
        low?: (number|null);

        /** Candle close */
        close?: (number|null);

        /** Candle volume */
        volume?: (number|Long|null);

        /** Candle timestamp */
        timestamp?: (number|Long|null);
    }

    /** Represents a Candle. */
    class Candle implements ICandle {

        /**
         * Constructs a new Candle.
         * @param [properties] Properties to set
         */
        constructor(properties?: market.ICandle);

        /** Candle open. */
        public open: number;

        /** Candle high. */
        public high: number;

        /** Candle low. */
        public low: number;

        /** Candle close. */
        public close: number;

        /** Candle volume. */
        public volume: (number|Long);

        /** Candle timestamp. */
        public timestamp: (number|Long);

        /**
         * Creates a new Candle instance using the specified properties.
         * @param [properties] Properties to set
         * @returns Candle instance
         */
        public static create(properties?: market.ICandle): market.Candle;

        /**
         * Encodes the specified Candle message. Does not implicitly {@link market.Candle.verify|verify} messages.
         * @param message Candle message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: market.ICandle, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified Candle message, length delimited. Does not implicitly {@link market.Candle.verify|verify} messages.
         * @param message Candle message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: market.ICandle, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a Candle message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns Candle
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): market.Candle;

        /**
         * Decodes a Candle message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns Candle
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): market.Candle;

        /**
         * Verifies a Candle message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a Candle message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns Candle
         */
        public static fromObject(object: { [k: string]: any }): market.Candle;

        /**
         * Creates a plain object from a Candle message. Also converts values to other types if specified.
         * @param message Candle
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: market.Candle, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this Candle to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for Candle
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a Quote. */
    interface IQuote {

        /** Quote bid */
        bid?: (number|null);

        /** Quote ask */
        ask?: (number|null);

        /** Quote bidSize */
        bidSize?: (number|Long|null);

        /** Quote askSize */
        askSize?: (number|Long|null);

        /** Quote timestampMs */
        timestampMs?: (number|Long|null);
    }

    /** Represents a Quote. */
    class Quote implements IQuote {

        /**
         * Constructs a new Quote.
         * @param [properties] Properties to set
         */
        constructor(properties?: market.IQuote);

        /** Quote bid. */
        public bid: number;

        /** Quote ask. */
        public ask: number;

        /** Quote bidSize. */
        public bidSize: (number|Long);

        /** Quote askSize. */
        public askSize: (number|Long);

        /** Quote timestampMs. */
        public timestampMs: (number|Long);

        /**
         * Creates a new Quote instance using the specified properties.
         * @param [properties] Properties to set
         * @returns Quote instance
         */
        public static create(properties?: market.IQuote): market.Quote;

        /**
         * Encodes the specified Quote message. Does not implicitly {@link market.Quote.verify|verify} messages.
         * @param message Quote message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: market.IQuote, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified Quote message, length delimited. Does not implicitly {@link market.Quote.verify|verify} messages.
         * @param message Quote message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: market.IQuote, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a Quote message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns Quote
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): market.Quote;

        /**
         * Decodes a Quote message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns Quote
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): market.Quote;

        /**
         * Verifies a Quote message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a Quote message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns Quote
         */
        public static fromObject(object: { [k: string]: any }): market.Quote;

        /**
         * Creates a plain object from a Quote message. Also converts values to other types if specified.
         * @param message Quote
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: market.Quote, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this Quote to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for Quote
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a FlowEvent. */
    interface IFlowEvent {

        /** FlowEvent type */
        type?: (string|null);

        /** FlowEvent tick */
        tick?: (market.ITick|null);

        /** FlowEvent sweep */
        sweep?: (market.ISweepEvent|null);

        /** FlowEvent absorption */
        absorption?: (market.IAbsorptionEvent|null);
    }

    /** Represents a FlowEvent. */
    class FlowEvent implements IFlowEvent {

        /**
         * Constructs a new FlowEvent.
         * @param [properties] Properties to set
         */
        constructor(properties?: market.IFlowEvent);

        /** FlowEvent type. */
        public type: string;

        /** FlowEvent tick. */
        public tick?: (market.ITick|null);

        /** FlowEvent sweep. */
        public sweep?: (market.ISweepEvent|null);

        /** FlowEvent absorption. */
        public absorption?: (market.IAbsorptionEvent|null);

        /**
         * Creates a new FlowEvent instance using the specified properties.
         * @param [properties] Properties to set
         * @returns FlowEvent instance
         */
        public static create(properties?: market.IFlowEvent): market.FlowEvent;

        /**
         * Encodes the specified FlowEvent message. Does not implicitly {@link market.FlowEvent.verify|verify} messages.
         * @param message FlowEvent message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: market.IFlowEvent, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified FlowEvent message, length delimited. Does not implicitly {@link market.FlowEvent.verify|verify} messages.
         * @param message FlowEvent message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: market.IFlowEvent, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a FlowEvent message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns FlowEvent
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): market.FlowEvent;

        /**
         * Decodes a FlowEvent message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns FlowEvent
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): market.FlowEvent;

        /**
         * Verifies a FlowEvent message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a FlowEvent message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns FlowEvent
         */
        public static fromObject(object: { [k: string]: any }): market.FlowEvent;

        /**
         * Creates a plain object from a FlowEvent message. Also converts values to other types if specified.
         * @param message FlowEvent
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: market.FlowEvent, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this FlowEvent to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for FlowEvent
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a SweepEvent. */
    interface ISweepEvent {

        /** SweepEvent direction */
        direction?: (string|null);

        /** SweepEvent notional */
        notional?: (number|null);

        /** SweepEvent strikes */
        strikes?: (number[]|null);
    }

    /** Represents a SweepEvent. */
    class SweepEvent implements ISweepEvent {

        /**
         * Constructs a new SweepEvent.
         * @param [properties] Properties to set
         */
        constructor(properties?: market.ISweepEvent);

        /** SweepEvent direction. */
        public direction: string;

        /** SweepEvent notional. */
        public notional: number;

        /** SweepEvent strikes. */
        public strikes: number[];

        /**
         * Creates a new SweepEvent instance using the specified properties.
         * @param [properties] Properties to set
         * @returns SweepEvent instance
         */
        public static create(properties?: market.ISweepEvent): market.SweepEvent;

        /**
         * Encodes the specified SweepEvent message. Does not implicitly {@link market.SweepEvent.verify|verify} messages.
         * @param message SweepEvent message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: market.ISweepEvent, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified SweepEvent message, length delimited. Does not implicitly {@link market.SweepEvent.verify|verify} messages.
         * @param message SweepEvent message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: market.ISweepEvent, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a SweepEvent message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns SweepEvent
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): market.SweepEvent;

        /**
         * Decodes a SweepEvent message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns SweepEvent
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): market.SweepEvent;

        /**
         * Verifies a SweepEvent message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a SweepEvent message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns SweepEvent
         */
        public static fromObject(object: { [k: string]: any }): market.SweepEvent;

        /**
         * Creates a plain object from a SweepEvent message. Also converts values to other types if specified.
         * @param message SweepEvent
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: market.SweepEvent, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this SweepEvent to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for SweepEvent
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of an AbsorptionEvent. */
    interface IAbsorptionEvent {

        /** AbsorptionEvent price */
        price?: (number|null);

        /** AbsorptionEvent direction */
        direction?: (string|null);

        /** AbsorptionEvent volume */
        volume?: (number|Long|null);
    }

    /** Represents an AbsorptionEvent. */
    class AbsorptionEvent implements IAbsorptionEvent {

        /**
         * Constructs a new AbsorptionEvent.
         * @param [properties] Properties to set
         */
        constructor(properties?: market.IAbsorptionEvent);

        /** AbsorptionEvent price. */
        public price: number;

        /** AbsorptionEvent direction. */
        public direction: string;

        /** AbsorptionEvent volume. */
        public volume: (number|Long);

        /**
         * Creates a new AbsorptionEvent instance using the specified properties.
         * @param [properties] Properties to set
         * @returns AbsorptionEvent instance
         */
        public static create(properties?: market.IAbsorptionEvent): market.AbsorptionEvent;

        /**
         * Encodes the specified AbsorptionEvent message. Does not implicitly {@link market.AbsorptionEvent.verify|verify} messages.
         * @param message AbsorptionEvent message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: market.IAbsorptionEvent, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified AbsorptionEvent message, length delimited. Does not implicitly {@link market.AbsorptionEvent.verify|verify} messages.
         * @param message AbsorptionEvent message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: market.IAbsorptionEvent, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes an AbsorptionEvent message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns AbsorptionEvent
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): market.AbsorptionEvent;

        /**
         * Decodes an AbsorptionEvent message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns AbsorptionEvent
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): market.AbsorptionEvent;

        /**
         * Verifies an AbsorptionEvent message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates an AbsorptionEvent message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns AbsorptionEvent
         */
        public static fromObject(object: { [k: string]: any }): market.AbsorptionEvent;

        /**
         * Creates a plain object from an AbsorptionEvent message. Also converts values to other types if specified.
         * @param message AbsorptionEvent
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: market.AbsorptionEvent, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this AbsorptionEvent to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for AbsorptionEvent
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a MarketMessage. */
    interface IMarketMessage {

        /** MarketMessage event */
        event?: (string|null);

        /** MarketMessage tick */
        tick?: (market.ITick|null);

        /** MarketMessage candle */
        candle?: (market.ICandle|null);

        /** MarketMessage quote */
        quote?: (market.IQuote|null);

        /** MarketMessage flow */
        flow?: (market.IFlowEvent|null);
    }

    /** Represents a MarketMessage. */
    class MarketMessage implements IMarketMessage {

        /**
         * Constructs a new MarketMessage.
         * @param [properties] Properties to set
         */
        constructor(properties?: market.IMarketMessage);

        /** MarketMessage event. */
        public event: string;

        /** MarketMessage tick. */
        public tick?: (market.ITick|null);

        /** MarketMessage candle. */
        public candle?: (market.ICandle|null);

        /** MarketMessage quote. */
        public quote?: (market.IQuote|null);

        /** MarketMessage flow. */
        public flow?: (market.IFlowEvent|null);

        /** MarketMessage payload. */
        public payload?: ("tick"|"candle"|"quote"|"flow");

        /**
         * Creates a new MarketMessage instance using the specified properties.
         * @param [properties] Properties to set
         * @returns MarketMessage instance
         */
        public static create(properties?: market.IMarketMessage): market.MarketMessage;

        /**
         * Encodes the specified MarketMessage message. Does not implicitly {@link market.MarketMessage.verify|verify} messages.
         * @param message MarketMessage message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: market.IMarketMessage, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified MarketMessage message, length delimited. Does not implicitly {@link market.MarketMessage.verify|verify} messages.
         * @param message MarketMessage message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: market.IMarketMessage, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a MarketMessage message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns MarketMessage
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): market.MarketMessage;

        /**
         * Decodes a MarketMessage message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns MarketMessage
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): market.MarketMessage;

        /**
         * Verifies a MarketMessage message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a MarketMessage message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns MarketMessage
         */
        public static fromObject(object: { [k: string]: any }): market.MarketMessage;

        /**
         * Creates a plain object from a MarketMessage message. Also converts values to other types if specified.
         * @param message MarketMessage
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: market.MarketMessage, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this MarketMessage to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for MarketMessage
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }
}
