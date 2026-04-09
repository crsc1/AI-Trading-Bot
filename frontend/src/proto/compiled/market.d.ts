import * as $protobuf from "protobufjs";
import Long = require("long");
/** Namespace market. */
export namespace market {

    /** TradeSide enum. */
    enum TradeSide {
        SIDE_UNKNOWN = 0,
        SIDE_BUY = 1,
        SIDE_SELL = 2
    }

    /** Properties of a Tick. */
    interface ITick {

        /** Tick price */
        price?: (number|null);

        /** Tick size */
        size?: (number|Long|null);

        /** Tick side */
        side?: (market.TradeSide|null);

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
        public side: market.TradeSide;

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

        /** Quote symbol */
        symbol?: (string|null);
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

        /** Quote symbol. */
        public symbol: string;

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

        /** Candle symbol */
        symbol?: (string|null);

        /** Candle isUpdate */
        isUpdate?: (boolean|null);
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

        /** Candle symbol. */
        public symbol: string;

        /** Candle isUpdate. */
        public isUpdate: boolean;

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

    /** Properties of a FootprintLevel. */
    interface IFootprintLevel {

        /** FootprintLevel price */
        price?: (number|null);

        /** FootprintLevel bidVol */
        bidVol?: (number|Long|null);

        /** FootprintLevel askVol */
        askVol?: (number|Long|null);
    }

    /** Represents a FootprintLevel. */
    class FootprintLevel implements IFootprintLevel {

        /**
         * Constructs a new FootprintLevel.
         * @param [properties] Properties to set
         */
        constructor(properties?: market.IFootprintLevel);

        /** FootprintLevel price. */
        public price: number;

        /** FootprintLevel bidVol. */
        public bidVol: (number|Long);

        /** FootprintLevel askVol. */
        public askVol: (number|Long);

        /**
         * Creates a new FootprintLevel instance using the specified properties.
         * @param [properties] Properties to set
         * @returns FootprintLevel instance
         */
        public static create(properties?: market.IFootprintLevel): market.FootprintLevel;

        /**
         * Encodes the specified FootprintLevel message. Does not implicitly {@link market.FootprintLevel.verify|verify} messages.
         * @param message FootprintLevel message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: market.IFootprintLevel, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified FootprintLevel message, length delimited. Does not implicitly {@link market.FootprintLevel.verify|verify} messages.
         * @param message FootprintLevel message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: market.IFootprintLevel, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a FootprintLevel message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns FootprintLevel
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): market.FootprintLevel;

        /**
         * Decodes a FootprintLevel message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns FootprintLevel
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): market.FootprintLevel;

        /**
         * Verifies a FootprintLevel message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a FootprintLevel message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns FootprintLevel
         */
        public static fromObject(object: { [k: string]: any }): market.FootprintLevel;

        /**
         * Creates a plain object from a FootprintLevel message. Also converts values to other types if specified.
         * @param message FootprintLevel
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: market.FootprintLevel, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this FootprintLevel to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for FootprintLevel
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a Footprint. */
    interface IFootprint {

        /** Footprint barTime */
        barTime?: (number|Long|null);

        /** Footprint levels */
        levels?: (market.IFootprintLevel[]|null);

        /** Footprint totalBuyVol */
        totalBuyVol?: (number|Long|null);

        /** Footprint totalSellVol */
        totalSellVol?: (number|Long|null);
    }

    /** Represents a Footprint. */
    class Footprint implements IFootprint {

        /**
         * Constructs a new Footprint.
         * @param [properties] Properties to set
         */
        constructor(properties?: market.IFootprint);

        /** Footprint barTime. */
        public barTime: (number|Long);

        /** Footprint levels. */
        public levels: market.IFootprintLevel[];

        /** Footprint totalBuyVol. */
        public totalBuyVol: (number|Long);

        /** Footprint totalSellVol. */
        public totalSellVol: (number|Long);

        /**
         * Creates a new Footprint instance using the specified properties.
         * @param [properties] Properties to set
         * @returns Footprint instance
         */
        public static create(properties?: market.IFootprint): market.Footprint;

        /**
         * Encodes the specified Footprint message. Does not implicitly {@link market.Footprint.verify|verify} messages.
         * @param message Footprint message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: market.IFootprint, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified Footprint message, length delimited. Does not implicitly {@link market.Footprint.verify|verify} messages.
         * @param message Footprint message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: market.IFootprint, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a Footprint message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns Footprint
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): market.Footprint;

        /**
         * Decodes a Footprint message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns Footprint
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): market.Footprint;

        /**
         * Verifies a Footprint message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a Footprint message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns Footprint
         */
        public static fromObject(object: { [k: string]: any }): market.Footprint;

        /**
         * Creates a plain object from a Footprint message. Also converts values to other types if specified.
         * @param message Footprint
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: market.Footprint, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this Footprint to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for Footprint
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a Cvd. */
    interface ICvd {

        /** Cvd value */
        value?: (number|Long|null);

        /** Cvd delta_1m */
        delta_1m?: (number|Long|null);

        /** Cvd delta_5m */
        delta_5m?: (number|Long|null);

        /** Cvd timestampMs */
        timestampMs?: (number|Long|null);
    }

    /** Represents a Cvd. */
    class Cvd implements ICvd {

        /**
         * Constructs a new Cvd.
         * @param [properties] Properties to set
         */
        constructor(properties?: market.ICvd);

        /** Cvd value. */
        public value: (number|Long);

        /** Cvd delta_1m. */
        public delta_1m: (number|Long);

        /** Cvd delta_5m. */
        public delta_5m: (number|Long);

        /** Cvd timestampMs. */
        public timestampMs: (number|Long);

        /**
         * Creates a new Cvd instance using the specified properties.
         * @param [properties] Properties to set
         * @returns Cvd instance
         */
        public static create(properties?: market.ICvd): market.Cvd;

        /**
         * Encodes the specified Cvd message. Does not implicitly {@link market.Cvd.verify|verify} messages.
         * @param message Cvd message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: market.ICvd, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified Cvd message, length delimited. Does not implicitly {@link market.Cvd.verify|verify} messages.
         * @param message Cvd message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: market.ICvd, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a Cvd message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns Cvd
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): market.Cvd;

        /**
         * Decodes a Cvd message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns Cvd
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): market.Cvd;

        /**
         * Verifies a Cvd message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a Cvd message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns Cvd
         */
        public static fromObject(object: { [k: string]: any }): market.Cvd;

        /**
         * Creates a plain object from a Cvd message. Also converts values to other types if specified.
         * @param message Cvd
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: market.Cvd, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this Cvd to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for Cvd
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a Sweep. */
    interface ISweep {

        /** Sweep price */
        price?: (number|null);

        /** Sweep size */
        size?: (number|Long|null);

        /** Sweep side */
        side?: (market.TradeSide|null);

        /** Sweep levelsHit */
        levelsHit?: (number|null);

        /** Sweep timestampMs */
        timestampMs?: (number|Long|null);
    }

    /** Represents a Sweep. */
    class Sweep implements ISweep {

        /**
         * Constructs a new Sweep.
         * @param [properties] Properties to set
         */
        constructor(properties?: market.ISweep);

        /** Sweep price. */
        public price: number;

        /** Sweep size. */
        public size: (number|Long);

        /** Sweep side. */
        public side: market.TradeSide;

        /** Sweep levelsHit. */
        public levelsHit: number;

        /** Sweep timestampMs. */
        public timestampMs: (number|Long);

        /**
         * Creates a new Sweep instance using the specified properties.
         * @param [properties] Properties to set
         * @returns Sweep instance
         */
        public static create(properties?: market.ISweep): market.Sweep;

        /**
         * Encodes the specified Sweep message. Does not implicitly {@link market.Sweep.verify|verify} messages.
         * @param message Sweep message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: market.ISweep, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified Sweep message, length delimited. Does not implicitly {@link market.Sweep.verify|verify} messages.
         * @param message Sweep message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: market.ISweep, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a Sweep message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns Sweep
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): market.Sweep;

        /**
         * Decodes a Sweep message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns Sweep
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): market.Sweep;

        /**
         * Verifies a Sweep message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a Sweep message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns Sweep
         */
        public static fromObject(object: { [k: string]: any }): market.Sweep;

        /**
         * Creates a plain object from a Sweep message. Also converts values to other types if specified.
         * @param message Sweep
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: market.Sweep, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this Sweep to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for Sweep
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of an Imbalance. */
    interface IImbalance {

        /** Imbalance price */
        price?: (number|null);

        /** Imbalance side */
        side?: (market.TradeSide|null);

        /** Imbalance ratio */
        ratio?: (number|null);

        /** Imbalance stacked */
        stacked?: (number|null);

        /** Imbalance timestampMs */
        timestampMs?: (number|Long|null);
    }

    /** Represents an Imbalance. */
    class Imbalance implements IImbalance {

        /**
         * Constructs a new Imbalance.
         * @param [properties] Properties to set
         */
        constructor(properties?: market.IImbalance);

        /** Imbalance price. */
        public price: number;

        /** Imbalance side. */
        public side: market.TradeSide;

        /** Imbalance ratio. */
        public ratio: number;

        /** Imbalance stacked. */
        public stacked: number;

        /** Imbalance timestampMs. */
        public timestampMs: (number|Long);

        /**
         * Creates a new Imbalance instance using the specified properties.
         * @param [properties] Properties to set
         * @returns Imbalance instance
         */
        public static create(properties?: market.IImbalance): market.Imbalance;

        /**
         * Encodes the specified Imbalance message. Does not implicitly {@link market.Imbalance.verify|verify} messages.
         * @param message Imbalance message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: market.IImbalance, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified Imbalance message, length delimited. Does not implicitly {@link market.Imbalance.verify|verify} messages.
         * @param message Imbalance message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: market.IImbalance, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes an Imbalance message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns Imbalance
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): market.Imbalance;

        /**
         * Decodes an Imbalance message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns Imbalance
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): market.Imbalance;

        /**
         * Verifies an Imbalance message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates an Imbalance message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns Imbalance
         */
        public static fromObject(object: { [k: string]: any }): market.Imbalance;

        /**
         * Creates a plain object from an Imbalance message. Also converts values to other types if specified.
         * @param message Imbalance
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: market.Imbalance, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this Imbalance to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for Imbalance
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of an Absorption. */
    interface IAbsorption {

        /** Absorption price */
        price?: (number|null);

        /** Absorption volume */
        volume?: (number|Long|null);

        /** Absorption side */
        side?: (market.TradeSide|null);

        /** Absorption held */
        held?: (boolean|null);

        /** Absorption timestampMs */
        timestampMs?: (number|Long|null);
    }

    /** Represents an Absorption. */
    class Absorption implements IAbsorption {

        /**
         * Constructs a new Absorption.
         * @param [properties] Properties to set
         */
        constructor(properties?: market.IAbsorption);

        /** Absorption price. */
        public price: number;

        /** Absorption volume. */
        public volume: (number|Long);

        /** Absorption side. */
        public side: market.TradeSide;

        /** Absorption held. */
        public held: boolean;

        /** Absorption timestampMs. */
        public timestampMs: (number|Long);

        /**
         * Creates a new Absorption instance using the specified properties.
         * @param [properties] Properties to set
         * @returns Absorption instance
         */
        public static create(properties?: market.IAbsorption): market.Absorption;

        /**
         * Encodes the specified Absorption message. Does not implicitly {@link market.Absorption.verify|verify} messages.
         * @param message Absorption message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: market.IAbsorption, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified Absorption message, length delimited. Does not implicitly {@link market.Absorption.verify|verify} messages.
         * @param message Absorption message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: market.IAbsorption, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes an Absorption message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns Absorption
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): market.Absorption;

        /**
         * Decodes an Absorption message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns Absorption
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): market.Absorption;

        /**
         * Verifies an Absorption message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates an Absorption message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns Absorption
         */
        public static fromObject(object: { [k: string]: any }): market.Absorption;

        /**
         * Creates a plain object from an Absorption message. Also converts values to other types if specified.
         * @param message Absorption
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: market.Absorption, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this Absorption to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for Absorption
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a DeltaFlip. */
    interface IDeltaFlip {

        /** DeltaFlip from */
        from?: (market.TradeSide|null);

        /** DeltaFlip to */
        to?: (market.TradeSide|null);

        /** DeltaFlip cvdAtFlip */
        cvdAtFlip?: (number|Long|null);

        /** DeltaFlip timestampMs */
        timestampMs?: (number|Long|null);
    }

    /** Represents a DeltaFlip. */
    class DeltaFlip implements IDeltaFlip {

        /**
         * Constructs a new DeltaFlip.
         * @param [properties] Properties to set
         */
        constructor(properties?: market.IDeltaFlip);

        /** DeltaFlip from. */
        public from: market.TradeSide;

        /** DeltaFlip to. */
        public to: market.TradeSide;

        /** DeltaFlip cvdAtFlip. */
        public cvdAtFlip: (number|Long);

        /** DeltaFlip timestampMs. */
        public timestampMs: (number|Long);

        /**
         * Creates a new DeltaFlip instance using the specified properties.
         * @param [properties] Properties to set
         * @returns DeltaFlip instance
         */
        public static create(properties?: market.IDeltaFlip): market.DeltaFlip;

        /**
         * Encodes the specified DeltaFlip message. Does not implicitly {@link market.DeltaFlip.verify|verify} messages.
         * @param message DeltaFlip message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: market.IDeltaFlip, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified DeltaFlip message, length delimited. Does not implicitly {@link market.DeltaFlip.verify|verify} messages.
         * @param message DeltaFlip message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: market.IDeltaFlip, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a DeltaFlip message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns DeltaFlip
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): market.DeltaFlip;

        /**
         * Decodes a DeltaFlip message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns DeltaFlip
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): market.DeltaFlip;

        /**
         * Verifies a DeltaFlip message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a DeltaFlip message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns DeltaFlip
         */
        public static fromObject(object: { [k: string]: any }): market.DeltaFlip;

        /**
         * Creates a plain object from a DeltaFlip message. Also converts values to other types if specified.
         * @param message DeltaFlip
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: market.DeltaFlip, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this DeltaFlip to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for DeltaFlip
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a LargeTrade. */
    interface ILargeTrade {

        /** LargeTrade price */
        price?: (number|null);

        /** LargeTrade size */
        size?: (number|Long|null);

        /** LargeTrade side */
        side?: (market.TradeSide|null);

        /** LargeTrade timestampMs */
        timestampMs?: (number|Long|null);
    }

    /** Represents a LargeTrade. */
    class LargeTrade implements ILargeTrade {

        /**
         * Constructs a new LargeTrade.
         * @param [properties] Properties to set
         */
        constructor(properties?: market.ILargeTrade);

        /** LargeTrade price. */
        public price: number;

        /** LargeTrade size. */
        public size: (number|Long);

        /** LargeTrade side. */
        public side: market.TradeSide;

        /** LargeTrade timestampMs. */
        public timestampMs: (number|Long);

        /**
         * Creates a new LargeTrade instance using the specified properties.
         * @param [properties] Properties to set
         * @returns LargeTrade instance
         */
        public static create(properties?: market.ILargeTrade): market.LargeTrade;

        /**
         * Encodes the specified LargeTrade message. Does not implicitly {@link market.LargeTrade.verify|verify} messages.
         * @param message LargeTrade message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: market.ILargeTrade, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified LargeTrade message, length delimited. Does not implicitly {@link market.LargeTrade.verify|verify} messages.
         * @param message LargeTrade message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: market.ILargeTrade, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a LargeTrade message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns LargeTrade
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): market.LargeTrade;

        /**
         * Decodes a LargeTrade message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns LargeTrade
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): market.LargeTrade;

        /**
         * Verifies a LargeTrade message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a LargeTrade message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns LargeTrade
         */
        public static fromObject(object: { [k: string]: any }): market.LargeTrade;

        /**
         * Creates a plain object from a LargeTrade message. Also converts values to other types if specified.
         * @param message LargeTrade
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: market.LargeTrade, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this LargeTrade to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for LargeTrade
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of an OptionTrade. */
    interface IOptionTrade {

        /** OptionTrade root */
        root?: (string|null);

        /** OptionTrade strike */
        strike?: (number|null);

        /** OptionTrade right */
        right?: (string|null);

        /** OptionTrade price */
        price?: (number|null);

        /** OptionTrade size */
        size?: (number|Long|null);

        /** OptionTrade premium */
        premium?: (number|null);

        /** OptionTrade side */
        side?: (string|null);

        /** OptionTrade iv */
        iv?: (number|null);

        /** OptionTrade delta */
        delta?: (number|null);

        /** OptionTrade gamma */
        gamma?: (number|null);

        /** OptionTrade vpin */
        vpin?: (number|null);

        /** OptionTrade sms */
        sms?: (number|null);

        /** OptionTrade expiration */
        expiration?: (number|null);

        /** OptionTrade exchange */
        exchange?: (string|null);

        /** OptionTrade timestampMs */
        timestampMs?: (number|Long|null);

        /** OptionTrade msOfDay */
        msOfDay?: (number|Long|null);

        /** OptionTrade condition */
        condition?: (number|null);
    }

    /** Represents an OptionTrade. */
    class OptionTrade implements IOptionTrade {

        /**
         * Constructs a new OptionTrade.
         * @param [properties] Properties to set
         */
        constructor(properties?: market.IOptionTrade);

        /** OptionTrade root. */
        public root: string;

        /** OptionTrade strike. */
        public strike: number;

        /** OptionTrade right. */
        public right: string;

        /** OptionTrade price. */
        public price: number;

        /** OptionTrade size. */
        public size: (number|Long);

        /** OptionTrade premium. */
        public premium: number;

        /** OptionTrade side. */
        public side: string;

        /** OptionTrade iv. */
        public iv: number;

        /** OptionTrade delta. */
        public delta: number;

        /** OptionTrade gamma. */
        public gamma: number;

        /** OptionTrade vpin. */
        public vpin: number;

        /** OptionTrade sms. */
        public sms: number;

        /** OptionTrade expiration. */
        public expiration: number;

        /** OptionTrade exchange. */
        public exchange: string;

        /** OptionTrade timestampMs. */
        public timestampMs: (number|Long);

        /** OptionTrade msOfDay. */
        public msOfDay: (number|Long);

        /** OptionTrade condition. */
        public condition: number;

        /**
         * Creates a new OptionTrade instance using the specified properties.
         * @param [properties] Properties to set
         * @returns OptionTrade instance
         */
        public static create(properties?: market.IOptionTrade): market.OptionTrade;

        /**
         * Encodes the specified OptionTrade message. Does not implicitly {@link market.OptionTrade.verify|verify} messages.
         * @param message OptionTrade message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: market.IOptionTrade, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified OptionTrade message, length delimited. Does not implicitly {@link market.OptionTrade.verify|verify} messages.
         * @param message OptionTrade message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: market.IOptionTrade, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes an OptionTrade message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns OptionTrade
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): market.OptionTrade;

        /**
         * Decodes an OptionTrade message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns OptionTrade
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): market.OptionTrade;

        /**
         * Verifies an OptionTrade message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates an OptionTrade message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns OptionTrade
         */
        public static fromObject(object: { [k: string]: any }): market.OptionTrade;

        /**
         * Creates a plain object from an OptionTrade message. Also converts values to other types if specified.
         * @param message OptionTrade
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: market.OptionTrade, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this OptionTrade to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for OptionTrade
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a Heartbeat. */
    interface IHeartbeat {

        /** Heartbeat timestampMs */
        timestampMs?: (number|Long|null);

        /** Heartbeat ticksProcessed */
        ticksProcessed?: (number|Long|null);

        /** Heartbeat lastPrice */
        lastPrice?: (number|null);

        /** Heartbeat dataSource */
        dataSource?: (string|null);
    }

    /** Represents a Heartbeat. */
    class Heartbeat implements IHeartbeat {

        /**
         * Constructs a new Heartbeat.
         * @param [properties] Properties to set
         */
        constructor(properties?: market.IHeartbeat);

        /** Heartbeat timestampMs. */
        public timestampMs: (number|Long);

        /** Heartbeat ticksProcessed. */
        public ticksProcessed: (number|Long);

        /** Heartbeat lastPrice. */
        public lastPrice: number;

        /** Heartbeat dataSource. */
        public dataSource: string;

        /**
         * Creates a new Heartbeat instance using the specified properties.
         * @param [properties] Properties to set
         * @returns Heartbeat instance
         */
        public static create(properties?: market.IHeartbeat): market.Heartbeat;

        /**
         * Encodes the specified Heartbeat message. Does not implicitly {@link market.Heartbeat.verify|verify} messages.
         * @param message Heartbeat message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: market.IHeartbeat, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified Heartbeat message, length delimited. Does not implicitly {@link market.Heartbeat.verify|verify} messages.
         * @param message Heartbeat message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: market.IHeartbeat, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a Heartbeat message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns Heartbeat
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): market.Heartbeat;

        /**
         * Decodes a Heartbeat message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns Heartbeat
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): market.Heartbeat;

        /**
         * Verifies a Heartbeat message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a Heartbeat message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns Heartbeat
         */
        public static fromObject(object: { [k: string]: any }): market.Heartbeat;

        /**
         * Creates a plain object from a Heartbeat message. Also converts values to other types if specified.
         * @param message Heartbeat
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: market.Heartbeat, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this Heartbeat to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for Heartbeat
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of an ExternalJson. */
    interface IExternalJson {

        /** ExternalJson json */
        json?: (string|null);
    }

    /** Represents an ExternalJson. */
    class ExternalJson implements IExternalJson {

        /**
         * Constructs a new ExternalJson.
         * @param [properties] Properties to set
         */
        constructor(properties?: market.IExternalJson);

        /** ExternalJson json. */
        public json: string;

        /**
         * Creates a new ExternalJson instance using the specified properties.
         * @param [properties] Properties to set
         * @returns ExternalJson instance
         */
        public static create(properties?: market.IExternalJson): market.ExternalJson;

        /**
         * Encodes the specified ExternalJson message. Does not implicitly {@link market.ExternalJson.verify|verify} messages.
         * @param message ExternalJson message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: market.IExternalJson, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified ExternalJson message, length delimited. Does not implicitly {@link market.ExternalJson.verify|verify} messages.
         * @param message ExternalJson message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: market.IExternalJson, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes an ExternalJson message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns ExternalJson
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): market.ExternalJson;

        /**
         * Decodes an ExternalJson message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns ExternalJson
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): market.ExternalJson;

        /**
         * Verifies an ExternalJson message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates an ExternalJson message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns ExternalJson
         */
        public static fromObject(object: { [k: string]: any }): market.ExternalJson;

        /**
         * Creates a plain object from an ExternalJson message. Also converts values to other types if specified.
         * @param message ExternalJson
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: market.ExternalJson, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this ExternalJson to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for ExternalJson
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a MarketMessage. */
    interface IMarketMessage {

        /** MarketMessage tick */
        tick?: (market.ITick|null);

        /** MarketMessage quote */
        quote?: (market.IQuote|null);

        /** MarketMessage candle */
        candle?: (market.ICandle|null);

        /** MarketMessage cvd */
        cvd?: (market.ICvd|null);

        /** MarketMessage footprint */
        footprint?: (market.IFootprint|null);

        /** MarketMessage sweep */
        sweep?: (market.ISweep|null);

        /** MarketMessage imbalance */
        imbalance?: (market.IImbalance|null);

        /** MarketMessage absorption */
        absorption?: (market.IAbsorption|null);

        /** MarketMessage deltaFlip */
        deltaFlip?: (market.IDeltaFlip|null);

        /** MarketMessage largeTrade */
        largeTrade?: (market.ILargeTrade|null);

        /** MarketMessage optionTrade */
        optionTrade?: (market.IOptionTrade|null);

        /** MarketMessage heartbeat */
        heartbeat?: (market.IHeartbeat|null);

        /** MarketMessage external */
        external?: (market.IExternalJson|null);
    }

    /** Represents a MarketMessage. */
    class MarketMessage implements IMarketMessage {

        /**
         * Constructs a new MarketMessage.
         * @param [properties] Properties to set
         */
        constructor(properties?: market.IMarketMessage);

        /** MarketMessage tick. */
        public tick?: (market.ITick|null);

        /** MarketMessage quote. */
        public quote?: (market.IQuote|null);

        /** MarketMessage candle. */
        public candle?: (market.ICandle|null);

        /** MarketMessage cvd. */
        public cvd?: (market.ICvd|null);

        /** MarketMessage footprint. */
        public footprint?: (market.IFootprint|null);

        /** MarketMessage sweep. */
        public sweep?: (market.ISweep|null);

        /** MarketMessage imbalance. */
        public imbalance?: (market.IImbalance|null);

        /** MarketMessage absorption. */
        public absorption?: (market.IAbsorption|null);

        /** MarketMessage deltaFlip. */
        public deltaFlip?: (market.IDeltaFlip|null);

        /** MarketMessage largeTrade. */
        public largeTrade?: (market.ILargeTrade|null);

        /** MarketMessage optionTrade. */
        public optionTrade?: (market.IOptionTrade|null);

        /** MarketMessage heartbeat. */
        public heartbeat?: (market.IHeartbeat|null);

        /** MarketMessage external. */
        public external?: (market.IExternalJson|null);

        /** MarketMessage payload. */
        public payload?: ("tick"|"quote"|"candle"|"cvd"|"footprint"|"sweep"|"imbalance"|"absorption"|"deltaFlip"|"largeTrade"|"optionTrade"|"heartbeat"|"external");

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
