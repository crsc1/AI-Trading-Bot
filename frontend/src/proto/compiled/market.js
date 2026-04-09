/*eslint-disable block-scoped-var, id-length, no-control-regex, no-magic-numbers, no-prototype-builtins, no-redeclare, no-shadow, no-var, sort-vars*/
import * as $protobuf from "protobufjs/minimal";

// Common aliases
const $Reader = $protobuf.Reader, $Writer = $protobuf.Writer, $util = $protobuf.util;

// Exported root namespace
const $root = $protobuf.roots["default"] || ($protobuf.roots["default"] = {});

export const market = $root.market = (() => {

    /**
     * Namespace market.
     * @exports market
     * @namespace
     */
    const market = {};

    /**
     * TradeSide enum.
     * @name market.TradeSide
     * @enum {number}
     * @property {number} SIDE_UNKNOWN=0 SIDE_UNKNOWN value
     * @property {number} SIDE_BUY=1 SIDE_BUY value
     * @property {number} SIDE_SELL=2 SIDE_SELL value
     */
    market.TradeSide = (function() {
        const valuesById = {}, values = Object.create(valuesById);
        values[valuesById[0] = "SIDE_UNKNOWN"] = 0;
        values[valuesById[1] = "SIDE_BUY"] = 1;
        values[valuesById[2] = "SIDE_SELL"] = 2;
        return values;
    })();

    market.Tick = (function() {

        /**
         * Properties of a Tick.
         * @memberof market
         * @interface ITick
         * @property {number|null} [price] Tick price
         * @property {number|Long|null} [size] Tick size
         * @property {market.TradeSide|null} [side] Tick side
         * @property {number|Long|null} [timestampMs] Tick timestampMs
         */

        /**
         * Constructs a new Tick.
         * @memberof market
         * @classdesc Represents a Tick.
         * @implements ITick
         * @constructor
         * @param {market.ITick=} [properties] Properties to set
         */
        function Tick(properties) {
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * Tick price.
         * @member {number} price
         * @memberof market.Tick
         * @instance
         */
        Tick.prototype.price = 0;

        /**
         * Tick size.
         * @member {number|Long} size
         * @memberof market.Tick
         * @instance
         */
        Tick.prototype.size = $util.Long ? $util.Long.fromBits(0,0,true) : 0;

        /**
         * Tick side.
         * @member {market.TradeSide} side
         * @memberof market.Tick
         * @instance
         */
        Tick.prototype.side = 0;

        /**
         * Tick timestampMs.
         * @member {number|Long} timestampMs
         * @memberof market.Tick
         * @instance
         */
        Tick.prototype.timestampMs = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * Creates a new Tick instance using the specified properties.
         * @function create
         * @memberof market.Tick
         * @static
         * @param {market.ITick=} [properties] Properties to set
         * @returns {market.Tick} Tick instance
         */
        Tick.create = function create(properties) {
            return new Tick(properties);
        };

        /**
         * Encodes the specified Tick message. Does not implicitly {@link market.Tick.verify|verify} messages.
         * @function encode
         * @memberof market.Tick
         * @static
         * @param {market.ITick} message Tick message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Tick.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.price != null && Object.hasOwnProperty.call(message, "price"))
                writer.uint32(/* id 1, wireType 1 =*/9).double(message.price);
            if (message.size != null && Object.hasOwnProperty.call(message, "size"))
                writer.uint32(/* id 2, wireType 0 =*/16).uint64(message.size);
            if (message.side != null && Object.hasOwnProperty.call(message, "side"))
                writer.uint32(/* id 3, wireType 0 =*/24).int32(message.side);
            if (message.timestampMs != null && Object.hasOwnProperty.call(message, "timestampMs"))
                writer.uint32(/* id 4, wireType 0 =*/32).int64(message.timestampMs);
            return writer;
        };

        /**
         * Encodes the specified Tick message, length delimited. Does not implicitly {@link market.Tick.verify|verify} messages.
         * @function encodeDelimited
         * @memberof market.Tick
         * @static
         * @param {market.ITick} message Tick message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Tick.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a Tick message from the specified reader or buffer.
         * @function decode
         * @memberof market.Tick
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {market.Tick} Tick
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Tick.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.market.Tick();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.price = reader.double();
                        break;
                    }
                case 2: {
                        message.size = reader.uint64();
                        break;
                    }
                case 3: {
                        message.side = reader.int32();
                        break;
                    }
                case 4: {
                        message.timestampMs = reader.int64();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a Tick message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof market.Tick
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {market.Tick} Tick
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Tick.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a Tick message.
         * @function verify
         * @memberof market.Tick
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        Tick.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.price != null && message.hasOwnProperty("price"))
                if (typeof message.price !== "number")
                    return "price: number expected";
            if (message.size != null && message.hasOwnProperty("size"))
                if (!$util.isInteger(message.size) && !(message.size && $util.isInteger(message.size.low) && $util.isInteger(message.size.high)))
                    return "size: integer|Long expected";
            if (message.side != null && message.hasOwnProperty("side"))
                switch (message.side) {
                default:
                    return "side: enum value expected";
                case 0:
                case 1:
                case 2:
                    break;
                }
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (!$util.isInteger(message.timestampMs) && !(message.timestampMs && $util.isInteger(message.timestampMs.low) && $util.isInteger(message.timestampMs.high)))
                    return "timestampMs: integer|Long expected";
            return null;
        };

        /**
         * Creates a Tick message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof market.Tick
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {market.Tick} Tick
         */
        Tick.fromObject = function fromObject(object) {
            if (object instanceof $root.market.Tick)
                return object;
            let message = new $root.market.Tick();
            if (object.price != null)
                message.price = Number(object.price);
            if (object.size != null)
                if ($util.Long)
                    (message.size = $util.Long.fromValue(object.size)).unsigned = true;
                else if (typeof object.size === "string")
                    message.size = parseInt(object.size, 10);
                else if (typeof object.size === "number")
                    message.size = object.size;
                else if (typeof object.size === "object")
                    message.size = new $util.LongBits(object.size.low >>> 0, object.size.high >>> 0).toNumber(true);
            switch (object.side) {
            default:
                if (typeof object.side === "number") {
                    message.side = object.side;
                    break;
                }
                break;
            case "SIDE_UNKNOWN":
            case 0:
                message.side = 0;
                break;
            case "SIDE_BUY":
            case 1:
                message.side = 1;
                break;
            case "SIDE_SELL":
            case 2:
                message.side = 2;
                break;
            }
            if (object.timestampMs != null)
                if ($util.Long)
                    (message.timestampMs = $util.Long.fromValue(object.timestampMs)).unsigned = false;
                else if (typeof object.timestampMs === "string")
                    message.timestampMs = parseInt(object.timestampMs, 10);
                else if (typeof object.timestampMs === "number")
                    message.timestampMs = object.timestampMs;
                else if (typeof object.timestampMs === "object")
                    message.timestampMs = new $util.LongBits(object.timestampMs.low >>> 0, object.timestampMs.high >>> 0).toNumber();
            return message;
        };

        /**
         * Creates a plain object from a Tick message. Also converts values to other types if specified.
         * @function toObject
         * @memberof market.Tick
         * @static
         * @param {market.Tick} message Tick
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        Tick.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.defaults) {
                object.price = 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, true);
                    object.size = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.size = options.longs === String ? "0" : 0;
                object.side = options.enums === String ? "SIDE_UNKNOWN" : 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.timestampMs = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.timestampMs = options.longs === String ? "0" : 0;
            }
            if (message.price != null && message.hasOwnProperty("price"))
                object.price = options.json && !isFinite(message.price) ? String(message.price) : message.price;
            if (message.size != null && message.hasOwnProperty("size"))
                if (typeof message.size === "number")
                    object.size = options.longs === String ? String(message.size) : message.size;
                else
                    object.size = options.longs === String ? $util.Long.prototype.toString.call(message.size) : options.longs === Number ? new $util.LongBits(message.size.low >>> 0, message.size.high >>> 0).toNumber(true) : message.size;
            if (message.side != null && message.hasOwnProperty("side"))
                object.side = options.enums === String ? $root.market.TradeSide[message.side] === undefined ? message.side : $root.market.TradeSide[message.side] : message.side;
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (typeof message.timestampMs === "number")
                    object.timestampMs = options.longs === String ? String(message.timestampMs) : message.timestampMs;
                else
                    object.timestampMs = options.longs === String ? $util.Long.prototype.toString.call(message.timestampMs) : options.longs === Number ? new $util.LongBits(message.timestampMs.low >>> 0, message.timestampMs.high >>> 0).toNumber() : message.timestampMs;
            return object;
        };

        /**
         * Converts this Tick to JSON.
         * @function toJSON
         * @memberof market.Tick
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        Tick.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for Tick
         * @function getTypeUrl
         * @memberof market.Tick
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        Tick.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/market.Tick";
        };

        return Tick;
    })();

    market.Quote = (function() {

        /**
         * Properties of a Quote.
         * @memberof market
         * @interface IQuote
         * @property {number|null} [bid] Quote bid
         * @property {number|null} [ask] Quote ask
         * @property {number|Long|null} [bidSize] Quote bidSize
         * @property {number|Long|null} [askSize] Quote askSize
         * @property {number|Long|null} [timestampMs] Quote timestampMs
         * @property {string|null} [symbol] Quote symbol
         */

        /**
         * Constructs a new Quote.
         * @memberof market
         * @classdesc Represents a Quote.
         * @implements IQuote
         * @constructor
         * @param {market.IQuote=} [properties] Properties to set
         */
        function Quote(properties) {
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * Quote bid.
         * @member {number} bid
         * @memberof market.Quote
         * @instance
         */
        Quote.prototype.bid = 0;

        /**
         * Quote ask.
         * @member {number} ask
         * @memberof market.Quote
         * @instance
         */
        Quote.prototype.ask = 0;

        /**
         * Quote bidSize.
         * @member {number|Long} bidSize
         * @memberof market.Quote
         * @instance
         */
        Quote.prototype.bidSize = $util.Long ? $util.Long.fromBits(0,0,true) : 0;

        /**
         * Quote askSize.
         * @member {number|Long} askSize
         * @memberof market.Quote
         * @instance
         */
        Quote.prototype.askSize = $util.Long ? $util.Long.fromBits(0,0,true) : 0;

        /**
         * Quote timestampMs.
         * @member {number|Long} timestampMs
         * @memberof market.Quote
         * @instance
         */
        Quote.prototype.timestampMs = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * Quote symbol.
         * @member {string} symbol
         * @memberof market.Quote
         * @instance
         */
        Quote.prototype.symbol = "";

        /**
         * Creates a new Quote instance using the specified properties.
         * @function create
         * @memberof market.Quote
         * @static
         * @param {market.IQuote=} [properties] Properties to set
         * @returns {market.Quote} Quote instance
         */
        Quote.create = function create(properties) {
            return new Quote(properties);
        };

        /**
         * Encodes the specified Quote message. Does not implicitly {@link market.Quote.verify|verify} messages.
         * @function encode
         * @memberof market.Quote
         * @static
         * @param {market.IQuote} message Quote message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Quote.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.bid != null && Object.hasOwnProperty.call(message, "bid"))
                writer.uint32(/* id 1, wireType 1 =*/9).double(message.bid);
            if (message.ask != null && Object.hasOwnProperty.call(message, "ask"))
                writer.uint32(/* id 2, wireType 1 =*/17).double(message.ask);
            if (message.bidSize != null && Object.hasOwnProperty.call(message, "bidSize"))
                writer.uint32(/* id 3, wireType 0 =*/24).uint64(message.bidSize);
            if (message.askSize != null && Object.hasOwnProperty.call(message, "askSize"))
                writer.uint32(/* id 4, wireType 0 =*/32).uint64(message.askSize);
            if (message.timestampMs != null && Object.hasOwnProperty.call(message, "timestampMs"))
                writer.uint32(/* id 5, wireType 0 =*/40).int64(message.timestampMs);
            if (message.symbol != null && Object.hasOwnProperty.call(message, "symbol"))
                writer.uint32(/* id 6, wireType 2 =*/50).string(message.symbol);
            return writer;
        };

        /**
         * Encodes the specified Quote message, length delimited. Does not implicitly {@link market.Quote.verify|verify} messages.
         * @function encodeDelimited
         * @memberof market.Quote
         * @static
         * @param {market.IQuote} message Quote message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Quote.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a Quote message from the specified reader or buffer.
         * @function decode
         * @memberof market.Quote
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {market.Quote} Quote
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Quote.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.market.Quote();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.bid = reader.double();
                        break;
                    }
                case 2: {
                        message.ask = reader.double();
                        break;
                    }
                case 3: {
                        message.bidSize = reader.uint64();
                        break;
                    }
                case 4: {
                        message.askSize = reader.uint64();
                        break;
                    }
                case 5: {
                        message.timestampMs = reader.int64();
                        break;
                    }
                case 6: {
                        message.symbol = reader.string();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a Quote message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof market.Quote
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {market.Quote} Quote
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Quote.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a Quote message.
         * @function verify
         * @memberof market.Quote
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        Quote.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.bid != null && message.hasOwnProperty("bid"))
                if (typeof message.bid !== "number")
                    return "bid: number expected";
            if (message.ask != null && message.hasOwnProperty("ask"))
                if (typeof message.ask !== "number")
                    return "ask: number expected";
            if (message.bidSize != null && message.hasOwnProperty("bidSize"))
                if (!$util.isInteger(message.bidSize) && !(message.bidSize && $util.isInteger(message.bidSize.low) && $util.isInteger(message.bidSize.high)))
                    return "bidSize: integer|Long expected";
            if (message.askSize != null && message.hasOwnProperty("askSize"))
                if (!$util.isInteger(message.askSize) && !(message.askSize && $util.isInteger(message.askSize.low) && $util.isInteger(message.askSize.high)))
                    return "askSize: integer|Long expected";
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (!$util.isInteger(message.timestampMs) && !(message.timestampMs && $util.isInteger(message.timestampMs.low) && $util.isInteger(message.timestampMs.high)))
                    return "timestampMs: integer|Long expected";
            if (message.symbol != null && message.hasOwnProperty("symbol"))
                if (!$util.isString(message.symbol))
                    return "symbol: string expected";
            return null;
        };

        /**
         * Creates a Quote message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof market.Quote
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {market.Quote} Quote
         */
        Quote.fromObject = function fromObject(object) {
            if (object instanceof $root.market.Quote)
                return object;
            let message = new $root.market.Quote();
            if (object.bid != null)
                message.bid = Number(object.bid);
            if (object.ask != null)
                message.ask = Number(object.ask);
            if (object.bidSize != null)
                if ($util.Long)
                    (message.bidSize = $util.Long.fromValue(object.bidSize)).unsigned = true;
                else if (typeof object.bidSize === "string")
                    message.bidSize = parseInt(object.bidSize, 10);
                else if (typeof object.bidSize === "number")
                    message.bidSize = object.bidSize;
                else if (typeof object.bidSize === "object")
                    message.bidSize = new $util.LongBits(object.bidSize.low >>> 0, object.bidSize.high >>> 0).toNumber(true);
            if (object.askSize != null)
                if ($util.Long)
                    (message.askSize = $util.Long.fromValue(object.askSize)).unsigned = true;
                else if (typeof object.askSize === "string")
                    message.askSize = parseInt(object.askSize, 10);
                else if (typeof object.askSize === "number")
                    message.askSize = object.askSize;
                else if (typeof object.askSize === "object")
                    message.askSize = new $util.LongBits(object.askSize.low >>> 0, object.askSize.high >>> 0).toNumber(true);
            if (object.timestampMs != null)
                if ($util.Long)
                    (message.timestampMs = $util.Long.fromValue(object.timestampMs)).unsigned = false;
                else if (typeof object.timestampMs === "string")
                    message.timestampMs = parseInt(object.timestampMs, 10);
                else if (typeof object.timestampMs === "number")
                    message.timestampMs = object.timestampMs;
                else if (typeof object.timestampMs === "object")
                    message.timestampMs = new $util.LongBits(object.timestampMs.low >>> 0, object.timestampMs.high >>> 0).toNumber();
            if (object.symbol != null)
                message.symbol = String(object.symbol);
            return message;
        };

        /**
         * Creates a plain object from a Quote message. Also converts values to other types if specified.
         * @function toObject
         * @memberof market.Quote
         * @static
         * @param {market.Quote} message Quote
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        Quote.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.defaults) {
                object.bid = 0;
                object.ask = 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, true);
                    object.bidSize = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.bidSize = options.longs === String ? "0" : 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, true);
                    object.askSize = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.askSize = options.longs === String ? "0" : 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.timestampMs = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.timestampMs = options.longs === String ? "0" : 0;
                object.symbol = "";
            }
            if (message.bid != null && message.hasOwnProperty("bid"))
                object.bid = options.json && !isFinite(message.bid) ? String(message.bid) : message.bid;
            if (message.ask != null && message.hasOwnProperty("ask"))
                object.ask = options.json && !isFinite(message.ask) ? String(message.ask) : message.ask;
            if (message.bidSize != null && message.hasOwnProperty("bidSize"))
                if (typeof message.bidSize === "number")
                    object.bidSize = options.longs === String ? String(message.bidSize) : message.bidSize;
                else
                    object.bidSize = options.longs === String ? $util.Long.prototype.toString.call(message.bidSize) : options.longs === Number ? new $util.LongBits(message.bidSize.low >>> 0, message.bidSize.high >>> 0).toNumber(true) : message.bidSize;
            if (message.askSize != null && message.hasOwnProperty("askSize"))
                if (typeof message.askSize === "number")
                    object.askSize = options.longs === String ? String(message.askSize) : message.askSize;
                else
                    object.askSize = options.longs === String ? $util.Long.prototype.toString.call(message.askSize) : options.longs === Number ? new $util.LongBits(message.askSize.low >>> 0, message.askSize.high >>> 0).toNumber(true) : message.askSize;
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (typeof message.timestampMs === "number")
                    object.timestampMs = options.longs === String ? String(message.timestampMs) : message.timestampMs;
                else
                    object.timestampMs = options.longs === String ? $util.Long.prototype.toString.call(message.timestampMs) : options.longs === Number ? new $util.LongBits(message.timestampMs.low >>> 0, message.timestampMs.high >>> 0).toNumber() : message.timestampMs;
            if (message.symbol != null && message.hasOwnProperty("symbol"))
                object.symbol = message.symbol;
            return object;
        };

        /**
         * Converts this Quote to JSON.
         * @function toJSON
         * @memberof market.Quote
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        Quote.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for Quote
         * @function getTypeUrl
         * @memberof market.Quote
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        Quote.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/market.Quote";
        };

        return Quote;
    })();

    market.Candle = (function() {

        /**
         * Properties of a Candle.
         * @memberof market
         * @interface ICandle
         * @property {number|null} [open] Candle open
         * @property {number|null} [high] Candle high
         * @property {number|null} [low] Candle low
         * @property {number|null} [close] Candle close
         * @property {number|Long|null} [volume] Candle volume
         * @property {number|Long|null} [timestamp] Candle timestamp
         * @property {string|null} [symbol] Candle symbol
         * @property {boolean|null} [isUpdate] Candle isUpdate
         */

        /**
         * Constructs a new Candle.
         * @memberof market
         * @classdesc Represents a Candle.
         * @implements ICandle
         * @constructor
         * @param {market.ICandle=} [properties] Properties to set
         */
        function Candle(properties) {
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * Candle open.
         * @member {number} open
         * @memberof market.Candle
         * @instance
         */
        Candle.prototype.open = 0;

        /**
         * Candle high.
         * @member {number} high
         * @memberof market.Candle
         * @instance
         */
        Candle.prototype.high = 0;

        /**
         * Candle low.
         * @member {number} low
         * @memberof market.Candle
         * @instance
         */
        Candle.prototype.low = 0;

        /**
         * Candle close.
         * @member {number} close
         * @memberof market.Candle
         * @instance
         */
        Candle.prototype.close = 0;

        /**
         * Candle volume.
         * @member {number|Long} volume
         * @memberof market.Candle
         * @instance
         */
        Candle.prototype.volume = $util.Long ? $util.Long.fromBits(0,0,true) : 0;

        /**
         * Candle timestamp.
         * @member {number|Long} timestamp
         * @memberof market.Candle
         * @instance
         */
        Candle.prototype.timestamp = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * Candle symbol.
         * @member {string} symbol
         * @memberof market.Candle
         * @instance
         */
        Candle.prototype.symbol = "";

        /**
         * Candle isUpdate.
         * @member {boolean} isUpdate
         * @memberof market.Candle
         * @instance
         */
        Candle.prototype.isUpdate = false;

        /**
         * Creates a new Candle instance using the specified properties.
         * @function create
         * @memberof market.Candle
         * @static
         * @param {market.ICandle=} [properties] Properties to set
         * @returns {market.Candle} Candle instance
         */
        Candle.create = function create(properties) {
            return new Candle(properties);
        };

        /**
         * Encodes the specified Candle message. Does not implicitly {@link market.Candle.verify|verify} messages.
         * @function encode
         * @memberof market.Candle
         * @static
         * @param {market.ICandle} message Candle message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Candle.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.open != null && Object.hasOwnProperty.call(message, "open"))
                writer.uint32(/* id 1, wireType 1 =*/9).double(message.open);
            if (message.high != null && Object.hasOwnProperty.call(message, "high"))
                writer.uint32(/* id 2, wireType 1 =*/17).double(message.high);
            if (message.low != null && Object.hasOwnProperty.call(message, "low"))
                writer.uint32(/* id 3, wireType 1 =*/25).double(message.low);
            if (message.close != null && Object.hasOwnProperty.call(message, "close"))
                writer.uint32(/* id 4, wireType 1 =*/33).double(message.close);
            if (message.volume != null && Object.hasOwnProperty.call(message, "volume"))
                writer.uint32(/* id 5, wireType 0 =*/40).uint64(message.volume);
            if (message.timestamp != null && Object.hasOwnProperty.call(message, "timestamp"))
                writer.uint32(/* id 6, wireType 0 =*/48).int64(message.timestamp);
            if (message.symbol != null && Object.hasOwnProperty.call(message, "symbol"))
                writer.uint32(/* id 7, wireType 2 =*/58).string(message.symbol);
            if (message.isUpdate != null && Object.hasOwnProperty.call(message, "isUpdate"))
                writer.uint32(/* id 8, wireType 0 =*/64).bool(message.isUpdate);
            return writer;
        };

        /**
         * Encodes the specified Candle message, length delimited. Does not implicitly {@link market.Candle.verify|verify} messages.
         * @function encodeDelimited
         * @memberof market.Candle
         * @static
         * @param {market.ICandle} message Candle message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Candle.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a Candle message from the specified reader or buffer.
         * @function decode
         * @memberof market.Candle
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {market.Candle} Candle
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Candle.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.market.Candle();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.open = reader.double();
                        break;
                    }
                case 2: {
                        message.high = reader.double();
                        break;
                    }
                case 3: {
                        message.low = reader.double();
                        break;
                    }
                case 4: {
                        message.close = reader.double();
                        break;
                    }
                case 5: {
                        message.volume = reader.uint64();
                        break;
                    }
                case 6: {
                        message.timestamp = reader.int64();
                        break;
                    }
                case 7: {
                        message.symbol = reader.string();
                        break;
                    }
                case 8: {
                        message.isUpdate = reader.bool();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a Candle message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof market.Candle
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {market.Candle} Candle
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Candle.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a Candle message.
         * @function verify
         * @memberof market.Candle
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        Candle.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.open != null && message.hasOwnProperty("open"))
                if (typeof message.open !== "number")
                    return "open: number expected";
            if (message.high != null && message.hasOwnProperty("high"))
                if (typeof message.high !== "number")
                    return "high: number expected";
            if (message.low != null && message.hasOwnProperty("low"))
                if (typeof message.low !== "number")
                    return "low: number expected";
            if (message.close != null && message.hasOwnProperty("close"))
                if (typeof message.close !== "number")
                    return "close: number expected";
            if (message.volume != null && message.hasOwnProperty("volume"))
                if (!$util.isInteger(message.volume) && !(message.volume && $util.isInteger(message.volume.low) && $util.isInteger(message.volume.high)))
                    return "volume: integer|Long expected";
            if (message.timestamp != null && message.hasOwnProperty("timestamp"))
                if (!$util.isInteger(message.timestamp) && !(message.timestamp && $util.isInteger(message.timestamp.low) && $util.isInteger(message.timestamp.high)))
                    return "timestamp: integer|Long expected";
            if (message.symbol != null && message.hasOwnProperty("symbol"))
                if (!$util.isString(message.symbol))
                    return "symbol: string expected";
            if (message.isUpdate != null && message.hasOwnProperty("isUpdate"))
                if (typeof message.isUpdate !== "boolean")
                    return "isUpdate: boolean expected";
            return null;
        };

        /**
         * Creates a Candle message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof market.Candle
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {market.Candle} Candle
         */
        Candle.fromObject = function fromObject(object) {
            if (object instanceof $root.market.Candle)
                return object;
            let message = new $root.market.Candle();
            if (object.open != null)
                message.open = Number(object.open);
            if (object.high != null)
                message.high = Number(object.high);
            if (object.low != null)
                message.low = Number(object.low);
            if (object.close != null)
                message.close = Number(object.close);
            if (object.volume != null)
                if ($util.Long)
                    (message.volume = $util.Long.fromValue(object.volume)).unsigned = true;
                else if (typeof object.volume === "string")
                    message.volume = parseInt(object.volume, 10);
                else if (typeof object.volume === "number")
                    message.volume = object.volume;
                else if (typeof object.volume === "object")
                    message.volume = new $util.LongBits(object.volume.low >>> 0, object.volume.high >>> 0).toNumber(true);
            if (object.timestamp != null)
                if ($util.Long)
                    (message.timestamp = $util.Long.fromValue(object.timestamp)).unsigned = false;
                else if (typeof object.timestamp === "string")
                    message.timestamp = parseInt(object.timestamp, 10);
                else if (typeof object.timestamp === "number")
                    message.timestamp = object.timestamp;
                else if (typeof object.timestamp === "object")
                    message.timestamp = new $util.LongBits(object.timestamp.low >>> 0, object.timestamp.high >>> 0).toNumber();
            if (object.symbol != null)
                message.symbol = String(object.symbol);
            if (object.isUpdate != null)
                message.isUpdate = Boolean(object.isUpdate);
            return message;
        };

        /**
         * Creates a plain object from a Candle message. Also converts values to other types if specified.
         * @function toObject
         * @memberof market.Candle
         * @static
         * @param {market.Candle} message Candle
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        Candle.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.defaults) {
                object.open = 0;
                object.high = 0;
                object.low = 0;
                object.close = 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, true);
                    object.volume = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.volume = options.longs === String ? "0" : 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.timestamp = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.timestamp = options.longs === String ? "0" : 0;
                object.symbol = "";
                object.isUpdate = false;
            }
            if (message.open != null && message.hasOwnProperty("open"))
                object.open = options.json && !isFinite(message.open) ? String(message.open) : message.open;
            if (message.high != null && message.hasOwnProperty("high"))
                object.high = options.json && !isFinite(message.high) ? String(message.high) : message.high;
            if (message.low != null && message.hasOwnProperty("low"))
                object.low = options.json && !isFinite(message.low) ? String(message.low) : message.low;
            if (message.close != null && message.hasOwnProperty("close"))
                object.close = options.json && !isFinite(message.close) ? String(message.close) : message.close;
            if (message.volume != null && message.hasOwnProperty("volume"))
                if (typeof message.volume === "number")
                    object.volume = options.longs === String ? String(message.volume) : message.volume;
                else
                    object.volume = options.longs === String ? $util.Long.prototype.toString.call(message.volume) : options.longs === Number ? new $util.LongBits(message.volume.low >>> 0, message.volume.high >>> 0).toNumber(true) : message.volume;
            if (message.timestamp != null && message.hasOwnProperty("timestamp"))
                if (typeof message.timestamp === "number")
                    object.timestamp = options.longs === String ? String(message.timestamp) : message.timestamp;
                else
                    object.timestamp = options.longs === String ? $util.Long.prototype.toString.call(message.timestamp) : options.longs === Number ? new $util.LongBits(message.timestamp.low >>> 0, message.timestamp.high >>> 0).toNumber() : message.timestamp;
            if (message.symbol != null && message.hasOwnProperty("symbol"))
                object.symbol = message.symbol;
            if (message.isUpdate != null && message.hasOwnProperty("isUpdate"))
                object.isUpdate = message.isUpdate;
            return object;
        };

        /**
         * Converts this Candle to JSON.
         * @function toJSON
         * @memberof market.Candle
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        Candle.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for Candle
         * @function getTypeUrl
         * @memberof market.Candle
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        Candle.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/market.Candle";
        };

        return Candle;
    })();

    market.FootprintLevel = (function() {

        /**
         * Properties of a FootprintLevel.
         * @memberof market
         * @interface IFootprintLevel
         * @property {number|null} [price] FootprintLevel price
         * @property {number|Long|null} [bidVol] FootprintLevel bidVol
         * @property {number|Long|null} [askVol] FootprintLevel askVol
         */

        /**
         * Constructs a new FootprintLevel.
         * @memberof market
         * @classdesc Represents a FootprintLevel.
         * @implements IFootprintLevel
         * @constructor
         * @param {market.IFootprintLevel=} [properties] Properties to set
         */
        function FootprintLevel(properties) {
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * FootprintLevel price.
         * @member {number} price
         * @memberof market.FootprintLevel
         * @instance
         */
        FootprintLevel.prototype.price = 0;

        /**
         * FootprintLevel bidVol.
         * @member {number|Long} bidVol
         * @memberof market.FootprintLevel
         * @instance
         */
        FootprintLevel.prototype.bidVol = $util.Long ? $util.Long.fromBits(0,0,true) : 0;

        /**
         * FootprintLevel askVol.
         * @member {number|Long} askVol
         * @memberof market.FootprintLevel
         * @instance
         */
        FootprintLevel.prototype.askVol = $util.Long ? $util.Long.fromBits(0,0,true) : 0;

        /**
         * Creates a new FootprintLevel instance using the specified properties.
         * @function create
         * @memberof market.FootprintLevel
         * @static
         * @param {market.IFootprintLevel=} [properties] Properties to set
         * @returns {market.FootprintLevel} FootprintLevel instance
         */
        FootprintLevel.create = function create(properties) {
            return new FootprintLevel(properties);
        };

        /**
         * Encodes the specified FootprintLevel message. Does not implicitly {@link market.FootprintLevel.verify|verify} messages.
         * @function encode
         * @memberof market.FootprintLevel
         * @static
         * @param {market.IFootprintLevel} message FootprintLevel message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        FootprintLevel.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.price != null && Object.hasOwnProperty.call(message, "price"))
                writer.uint32(/* id 1, wireType 1 =*/9).double(message.price);
            if (message.bidVol != null && Object.hasOwnProperty.call(message, "bidVol"))
                writer.uint32(/* id 2, wireType 0 =*/16).uint64(message.bidVol);
            if (message.askVol != null && Object.hasOwnProperty.call(message, "askVol"))
                writer.uint32(/* id 3, wireType 0 =*/24).uint64(message.askVol);
            return writer;
        };

        /**
         * Encodes the specified FootprintLevel message, length delimited. Does not implicitly {@link market.FootprintLevel.verify|verify} messages.
         * @function encodeDelimited
         * @memberof market.FootprintLevel
         * @static
         * @param {market.IFootprintLevel} message FootprintLevel message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        FootprintLevel.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a FootprintLevel message from the specified reader or buffer.
         * @function decode
         * @memberof market.FootprintLevel
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {market.FootprintLevel} FootprintLevel
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        FootprintLevel.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.market.FootprintLevel();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.price = reader.double();
                        break;
                    }
                case 2: {
                        message.bidVol = reader.uint64();
                        break;
                    }
                case 3: {
                        message.askVol = reader.uint64();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a FootprintLevel message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof market.FootprintLevel
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {market.FootprintLevel} FootprintLevel
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        FootprintLevel.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a FootprintLevel message.
         * @function verify
         * @memberof market.FootprintLevel
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        FootprintLevel.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.price != null && message.hasOwnProperty("price"))
                if (typeof message.price !== "number")
                    return "price: number expected";
            if (message.bidVol != null && message.hasOwnProperty("bidVol"))
                if (!$util.isInteger(message.bidVol) && !(message.bidVol && $util.isInteger(message.bidVol.low) && $util.isInteger(message.bidVol.high)))
                    return "bidVol: integer|Long expected";
            if (message.askVol != null && message.hasOwnProperty("askVol"))
                if (!$util.isInteger(message.askVol) && !(message.askVol && $util.isInteger(message.askVol.low) && $util.isInteger(message.askVol.high)))
                    return "askVol: integer|Long expected";
            return null;
        };

        /**
         * Creates a FootprintLevel message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof market.FootprintLevel
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {market.FootprintLevel} FootprintLevel
         */
        FootprintLevel.fromObject = function fromObject(object) {
            if (object instanceof $root.market.FootprintLevel)
                return object;
            let message = new $root.market.FootprintLevel();
            if (object.price != null)
                message.price = Number(object.price);
            if (object.bidVol != null)
                if ($util.Long)
                    (message.bidVol = $util.Long.fromValue(object.bidVol)).unsigned = true;
                else if (typeof object.bidVol === "string")
                    message.bidVol = parseInt(object.bidVol, 10);
                else if (typeof object.bidVol === "number")
                    message.bidVol = object.bidVol;
                else if (typeof object.bidVol === "object")
                    message.bidVol = new $util.LongBits(object.bidVol.low >>> 0, object.bidVol.high >>> 0).toNumber(true);
            if (object.askVol != null)
                if ($util.Long)
                    (message.askVol = $util.Long.fromValue(object.askVol)).unsigned = true;
                else if (typeof object.askVol === "string")
                    message.askVol = parseInt(object.askVol, 10);
                else if (typeof object.askVol === "number")
                    message.askVol = object.askVol;
                else if (typeof object.askVol === "object")
                    message.askVol = new $util.LongBits(object.askVol.low >>> 0, object.askVol.high >>> 0).toNumber(true);
            return message;
        };

        /**
         * Creates a plain object from a FootprintLevel message. Also converts values to other types if specified.
         * @function toObject
         * @memberof market.FootprintLevel
         * @static
         * @param {market.FootprintLevel} message FootprintLevel
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        FootprintLevel.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.defaults) {
                object.price = 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, true);
                    object.bidVol = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.bidVol = options.longs === String ? "0" : 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, true);
                    object.askVol = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.askVol = options.longs === String ? "0" : 0;
            }
            if (message.price != null && message.hasOwnProperty("price"))
                object.price = options.json && !isFinite(message.price) ? String(message.price) : message.price;
            if (message.bidVol != null && message.hasOwnProperty("bidVol"))
                if (typeof message.bidVol === "number")
                    object.bidVol = options.longs === String ? String(message.bidVol) : message.bidVol;
                else
                    object.bidVol = options.longs === String ? $util.Long.prototype.toString.call(message.bidVol) : options.longs === Number ? new $util.LongBits(message.bidVol.low >>> 0, message.bidVol.high >>> 0).toNumber(true) : message.bidVol;
            if (message.askVol != null && message.hasOwnProperty("askVol"))
                if (typeof message.askVol === "number")
                    object.askVol = options.longs === String ? String(message.askVol) : message.askVol;
                else
                    object.askVol = options.longs === String ? $util.Long.prototype.toString.call(message.askVol) : options.longs === Number ? new $util.LongBits(message.askVol.low >>> 0, message.askVol.high >>> 0).toNumber(true) : message.askVol;
            return object;
        };

        /**
         * Converts this FootprintLevel to JSON.
         * @function toJSON
         * @memberof market.FootprintLevel
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        FootprintLevel.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for FootprintLevel
         * @function getTypeUrl
         * @memberof market.FootprintLevel
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        FootprintLevel.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/market.FootprintLevel";
        };

        return FootprintLevel;
    })();

    market.Footprint = (function() {

        /**
         * Properties of a Footprint.
         * @memberof market
         * @interface IFootprint
         * @property {number|Long|null} [barTime] Footprint barTime
         * @property {Array.<market.IFootprintLevel>|null} [levels] Footprint levels
         * @property {number|Long|null} [totalBuyVol] Footprint totalBuyVol
         * @property {number|Long|null} [totalSellVol] Footprint totalSellVol
         */

        /**
         * Constructs a new Footprint.
         * @memberof market
         * @classdesc Represents a Footprint.
         * @implements IFootprint
         * @constructor
         * @param {market.IFootprint=} [properties] Properties to set
         */
        function Footprint(properties) {
            this.levels = [];
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * Footprint barTime.
         * @member {number|Long} barTime
         * @memberof market.Footprint
         * @instance
         */
        Footprint.prototype.barTime = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * Footprint levels.
         * @member {Array.<market.IFootprintLevel>} levels
         * @memberof market.Footprint
         * @instance
         */
        Footprint.prototype.levels = $util.emptyArray;

        /**
         * Footprint totalBuyVol.
         * @member {number|Long} totalBuyVol
         * @memberof market.Footprint
         * @instance
         */
        Footprint.prototype.totalBuyVol = $util.Long ? $util.Long.fromBits(0,0,true) : 0;

        /**
         * Footprint totalSellVol.
         * @member {number|Long} totalSellVol
         * @memberof market.Footprint
         * @instance
         */
        Footprint.prototype.totalSellVol = $util.Long ? $util.Long.fromBits(0,0,true) : 0;

        /**
         * Creates a new Footprint instance using the specified properties.
         * @function create
         * @memberof market.Footprint
         * @static
         * @param {market.IFootprint=} [properties] Properties to set
         * @returns {market.Footprint} Footprint instance
         */
        Footprint.create = function create(properties) {
            return new Footprint(properties);
        };

        /**
         * Encodes the specified Footprint message. Does not implicitly {@link market.Footprint.verify|verify} messages.
         * @function encode
         * @memberof market.Footprint
         * @static
         * @param {market.IFootprint} message Footprint message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Footprint.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.barTime != null && Object.hasOwnProperty.call(message, "barTime"))
                writer.uint32(/* id 1, wireType 0 =*/8).int64(message.barTime);
            if (message.levels != null && message.levels.length)
                for (let i = 0; i < message.levels.length; ++i)
                    $root.market.FootprintLevel.encode(message.levels[i], writer.uint32(/* id 2, wireType 2 =*/18).fork()).ldelim();
            if (message.totalBuyVol != null && Object.hasOwnProperty.call(message, "totalBuyVol"))
                writer.uint32(/* id 3, wireType 0 =*/24).uint64(message.totalBuyVol);
            if (message.totalSellVol != null && Object.hasOwnProperty.call(message, "totalSellVol"))
                writer.uint32(/* id 4, wireType 0 =*/32).uint64(message.totalSellVol);
            return writer;
        };

        /**
         * Encodes the specified Footprint message, length delimited. Does not implicitly {@link market.Footprint.verify|verify} messages.
         * @function encodeDelimited
         * @memberof market.Footprint
         * @static
         * @param {market.IFootprint} message Footprint message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Footprint.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a Footprint message from the specified reader or buffer.
         * @function decode
         * @memberof market.Footprint
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {market.Footprint} Footprint
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Footprint.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.market.Footprint();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.barTime = reader.int64();
                        break;
                    }
                case 2: {
                        if (!(message.levels && message.levels.length))
                            message.levels = [];
                        message.levels.push($root.market.FootprintLevel.decode(reader, reader.uint32()));
                        break;
                    }
                case 3: {
                        message.totalBuyVol = reader.uint64();
                        break;
                    }
                case 4: {
                        message.totalSellVol = reader.uint64();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a Footprint message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof market.Footprint
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {market.Footprint} Footprint
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Footprint.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a Footprint message.
         * @function verify
         * @memberof market.Footprint
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        Footprint.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.barTime != null && message.hasOwnProperty("barTime"))
                if (!$util.isInteger(message.barTime) && !(message.barTime && $util.isInteger(message.barTime.low) && $util.isInteger(message.barTime.high)))
                    return "barTime: integer|Long expected";
            if (message.levels != null && message.hasOwnProperty("levels")) {
                if (!Array.isArray(message.levels))
                    return "levels: array expected";
                for (let i = 0; i < message.levels.length; ++i) {
                    let error = $root.market.FootprintLevel.verify(message.levels[i]);
                    if (error)
                        return "levels." + error;
                }
            }
            if (message.totalBuyVol != null && message.hasOwnProperty("totalBuyVol"))
                if (!$util.isInteger(message.totalBuyVol) && !(message.totalBuyVol && $util.isInteger(message.totalBuyVol.low) && $util.isInteger(message.totalBuyVol.high)))
                    return "totalBuyVol: integer|Long expected";
            if (message.totalSellVol != null && message.hasOwnProperty("totalSellVol"))
                if (!$util.isInteger(message.totalSellVol) && !(message.totalSellVol && $util.isInteger(message.totalSellVol.low) && $util.isInteger(message.totalSellVol.high)))
                    return "totalSellVol: integer|Long expected";
            return null;
        };

        /**
         * Creates a Footprint message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof market.Footprint
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {market.Footprint} Footprint
         */
        Footprint.fromObject = function fromObject(object) {
            if (object instanceof $root.market.Footprint)
                return object;
            let message = new $root.market.Footprint();
            if (object.barTime != null)
                if ($util.Long)
                    (message.barTime = $util.Long.fromValue(object.barTime)).unsigned = false;
                else if (typeof object.barTime === "string")
                    message.barTime = parseInt(object.barTime, 10);
                else if (typeof object.barTime === "number")
                    message.barTime = object.barTime;
                else if (typeof object.barTime === "object")
                    message.barTime = new $util.LongBits(object.barTime.low >>> 0, object.barTime.high >>> 0).toNumber();
            if (object.levels) {
                if (!Array.isArray(object.levels))
                    throw TypeError(".market.Footprint.levels: array expected");
                message.levels = [];
                for (let i = 0; i < object.levels.length; ++i) {
                    if (typeof object.levels[i] !== "object")
                        throw TypeError(".market.Footprint.levels: object expected");
                    message.levels[i] = $root.market.FootprintLevel.fromObject(object.levels[i]);
                }
            }
            if (object.totalBuyVol != null)
                if ($util.Long)
                    (message.totalBuyVol = $util.Long.fromValue(object.totalBuyVol)).unsigned = true;
                else if (typeof object.totalBuyVol === "string")
                    message.totalBuyVol = parseInt(object.totalBuyVol, 10);
                else if (typeof object.totalBuyVol === "number")
                    message.totalBuyVol = object.totalBuyVol;
                else if (typeof object.totalBuyVol === "object")
                    message.totalBuyVol = new $util.LongBits(object.totalBuyVol.low >>> 0, object.totalBuyVol.high >>> 0).toNumber(true);
            if (object.totalSellVol != null)
                if ($util.Long)
                    (message.totalSellVol = $util.Long.fromValue(object.totalSellVol)).unsigned = true;
                else if (typeof object.totalSellVol === "string")
                    message.totalSellVol = parseInt(object.totalSellVol, 10);
                else if (typeof object.totalSellVol === "number")
                    message.totalSellVol = object.totalSellVol;
                else if (typeof object.totalSellVol === "object")
                    message.totalSellVol = new $util.LongBits(object.totalSellVol.low >>> 0, object.totalSellVol.high >>> 0).toNumber(true);
            return message;
        };

        /**
         * Creates a plain object from a Footprint message. Also converts values to other types if specified.
         * @function toObject
         * @memberof market.Footprint
         * @static
         * @param {market.Footprint} message Footprint
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        Footprint.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.arrays || options.defaults)
                object.levels = [];
            if (options.defaults) {
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.barTime = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.barTime = options.longs === String ? "0" : 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, true);
                    object.totalBuyVol = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.totalBuyVol = options.longs === String ? "0" : 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, true);
                    object.totalSellVol = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.totalSellVol = options.longs === String ? "0" : 0;
            }
            if (message.barTime != null && message.hasOwnProperty("barTime"))
                if (typeof message.barTime === "number")
                    object.barTime = options.longs === String ? String(message.barTime) : message.barTime;
                else
                    object.barTime = options.longs === String ? $util.Long.prototype.toString.call(message.barTime) : options.longs === Number ? new $util.LongBits(message.barTime.low >>> 0, message.barTime.high >>> 0).toNumber() : message.barTime;
            if (message.levels && message.levels.length) {
                object.levels = [];
                for (let j = 0; j < message.levels.length; ++j)
                    object.levels[j] = $root.market.FootprintLevel.toObject(message.levels[j], options);
            }
            if (message.totalBuyVol != null && message.hasOwnProperty("totalBuyVol"))
                if (typeof message.totalBuyVol === "number")
                    object.totalBuyVol = options.longs === String ? String(message.totalBuyVol) : message.totalBuyVol;
                else
                    object.totalBuyVol = options.longs === String ? $util.Long.prototype.toString.call(message.totalBuyVol) : options.longs === Number ? new $util.LongBits(message.totalBuyVol.low >>> 0, message.totalBuyVol.high >>> 0).toNumber(true) : message.totalBuyVol;
            if (message.totalSellVol != null && message.hasOwnProperty("totalSellVol"))
                if (typeof message.totalSellVol === "number")
                    object.totalSellVol = options.longs === String ? String(message.totalSellVol) : message.totalSellVol;
                else
                    object.totalSellVol = options.longs === String ? $util.Long.prototype.toString.call(message.totalSellVol) : options.longs === Number ? new $util.LongBits(message.totalSellVol.low >>> 0, message.totalSellVol.high >>> 0).toNumber(true) : message.totalSellVol;
            return object;
        };

        /**
         * Converts this Footprint to JSON.
         * @function toJSON
         * @memberof market.Footprint
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        Footprint.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for Footprint
         * @function getTypeUrl
         * @memberof market.Footprint
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        Footprint.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/market.Footprint";
        };

        return Footprint;
    })();

    market.Cvd = (function() {

        /**
         * Properties of a Cvd.
         * @memberof market
         * @interface ICvd
         * @property {number|Long|null} [value] Cvd value
         * @property {number|Long|null} [delta_1m] Cvd delta_1m
         * @property {number|Long|null} [delta_5m] Cvd delta_5m
         * @property {number|Long|null} [timestampMs] Cvd timestampMs
         */

        /**
         * Constructs a new Cvd.
         * @memberof market
         * @classdesc Represents a Cvd.
         * @implements ICvd
         * @constructor
         * @param {market.ICvd=} [properties] Properties to set
         */
        function Cvd(properties) {
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * Cvd value.
         * @member {number|Long} value
         * @memberof market.Cvd
         * @instance
         */
        Cvd.prototype.value = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * Cvd delta_1m.
         * @member {number|Long} delta_1m
         * @memberof market.Cvd
         * @instance
         */
        Cvd.prototype.delta_1m = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * Cvd delta_5m.
         * @member {number|Long} delta_5m
         * @memberof market.Cvd
         * @instance
         */
        Cvd.prototype.delta_5m = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * Cvd timestampMs.
         * @member {number|Long} timestampMs
         * @memberof market.Cvd
         * @instance
         */
        Cvd.prototype.timestampMs = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * Creates a new Cvd instance using the specified properties.
         * @function create
         * @memberof market.Cvd
         * @static
         * @param {market.ICvd=} [properties] Properties to set
         * @returns {market.Cvd} Cvd instance
         */
        Cvd.create = function create(properties) {
            return new Cvd(properties);
        };

        /**
         * Encodes the specified Cvd message. Does not implicitly {@link market.Cvd.verify|verify} messages.
         * @function encode
         * @memberof market.Cvd
         * @static
         * @param {market.ICvd} message Cvd message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Cvd.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.value != null && Object.hasOwnProperty.call(message, "value"))
                writer.uint32(/* id 1, wireType 0 =*/8).int64(message.value);
            if (message.delta_1m != null && Object.hasOwnProperty.call(message, "delta_1m"))
                writer.uint32(/* id 2, wireType 0 =*/16).int64(message.delta_1m);
            if (message.delta_5m != null && Object.hasOwnProperty.call(message, "delta_5m"))
                writer.uint32(/* id 3, wireType 0 =*/24).int64(message.delta_5m);
            if (message.timestampMs != null && Object.hasOwnProperty.call(message, "timestampMs"))
                writer.uint32(/* id 4, wireType 0 =*/32).int64(message.timestampMs);
            return writer;
        };

        /**
         * Encodes the specified Cvd message, length delimited. Does not implicitly {@link market.Cvd.verify|verify} messages.
         * @function encodeDelimited
         * @memberof market.Cvd
         * @static
         * @param {market.ICvd} message Cvd message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Cvd.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a Cvd message from the specified reader or buffer.
         * @function decode
         * @memberof market.Cvd
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {market.Cvd} Cvd
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Cvd.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.market.Cvd();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.value = reader.int64();
                        break;
                    }
                case 2: {
                        message.delta_1m = reader.int64();
                        break;
                    }
                case 3: {
                        message.delta_5m = reader.int64();
                        break;
                    }
                case 4: {
                        message.timestampMs = reader.int64();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a Cvd message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof market.Cvd
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {market.Cvd} Cvd
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Cvd.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a Cvd message.
         * @function verify
         * @memberof market.Cvd
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        Cvd.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.value != null && message.hasOwnProperty("value"))
                if (!$util.isInteger(message.value) && !(message.value && $util.isInteger(message.value.low) && $util.isInteger(message.value.high)))
                    return "value: integer|Long expected";
            if (message.delta_1m != null && message.hasOwnProperty("delta_1m"))
                if (!$util.isInteger(message.delta_1m) && !(message.delta_1m && $util.isInteger(message.delta_1m.low) && $util.isInteger(message.delta_1m.high)))
                    return "delta_1m: integer|Long expected";
            if (message.delta_5m != null && message.hasOwnProperty("delta_5m"))
                if (!$util.isInteger(message.delta_5m) && !(message.delta_5m && $util.isInteger(message.delta_5m.low) && $util.isInteger(message.delta_5m.high)))
                    return "delta_5m: integer|Long expected";
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (!$util.isInteger(message.timestampMs) && !(message.timestampMs && $util.isInteger(message.timestampMs.low) && $util.isInteger(message.timestampMs.high)))
                    return "timestampMs: integer|Long expected";
            return null;
        };

        /**
         * Creates a Cvd message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof market.Cvd
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {market.Cvd} Cvd
         */
        Cvd.fromObject = function fromObject(object) {
            if (object instanceof $root.market.Cvd)
                return object;
            let message = new $root.market.Cvd();
            if (object.value != null)
                if ($util.Long)
                    (message.value = $util.Long.fromValue(object.value)).unsigned = false;
                else if (typeof object.value === "string")
                    message.value = parseInt(object.value, 10);
                else if (typeof object.value === "number")
                    message.value = object.value;
                else if (typeof object.value === "object")
                    message.value = new $util.LongBits(object.value.low >>> 0, object.value.high >>> 0).toNumber();
            if (object.delta_1m != null)
                if ($util.Long)
                    (message.delta_1m = $util.Long.fromValue(object.delta_1m)).unsigned = false;
                else if (typeof object.delta_1m === "string")
                    message.delta_1m = parseInt(object.delta_1m, 10);
                else if (typeof object.delta_1m === "number")
                    message.delta_1m = object.delta_1m;
                else if (typeof object.delta_1m === "object")
                    message.delta_1m = new $util.LongBits(object.delta_1m.low >>> 0, object.delta_1m.high >>> 0).toNumber();
            if (object.delta_5m != null)
                if ($util.Long)
                    (message.delta_5m = $util.Long.fromValue(object.delta_5m)).unsigned = false;
                else if (typeof object.delta_5m === "string")
                    message.delta_5m = parseInt(object.delta_5m, 10);
                else if (typeof object.delta_5m === "number")
                    message.delta_5m = object.delta_5m;
                else if (typeof object.delta_5m === "object")
                    message.delta_5m = new $util.LongBits(object.delta_5m.low >>> 0, object.delta_5m.high >>> 0).toNumber();
            if (object.timestampMs != null)
                if ($util.Long)
                    (message.timestampMs = $util.Long.fromValue(object.timestampMs)).unsigned = false;
                else if (typeof object.timestampMs === "string")
                    message.timestampMs = parseInt(object.timestampMs, 10);
                else if (typeof object.timestampMs === "number")
                    message.timestampMs = object.timestampMs;
                else if (typeof object.timestampMs === "object")
                    message.timestampMs = new $util.LongBits(object.timestampMs.low >>> 0, object.timestampMs.high >>> 0).toNumber();
            return message;
        };

        /**
         * Creates a plain object from a Cvd message. Also converts values to other types if specified.
         * @function toObject
         * @memberof market.Cvd
         * @static
         * @param {market.Cvd} message Cvd
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        Cvd.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.defaults) {
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.value = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.value = options.longs === String ? "0" : 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.delta_1m = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.delta_1m = options.longs === String ? "0" : 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.delta_5m = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.delta_5m = options.longs === String ? "0" : 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.timestampMs = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.timestampMs = options.longs === String ? "0" : 0;
            }
            if (message.value != null && message.hasOwnProperty("value"))
                if (typeof message.value === "number")
                    object.value = options.longs === String ? String(message.value) : message.value;
                else
                    object.value = options.longs === String ? $util.Long.prototype.toString.call(message.value) : options.longs === Number ? new $util.LongBits(message.value.low >>> 0, message.value.high >>> 0).toNumber() : message.value;
            if (message.delta_1m != null && message.hasOwnProperty("delta_1m"))
                if (typeof message.delta_1m === "number")
                    object.delta_1m = options.longs === String ? String(message.delta_1m) : message.delta_1m;
                else
                    object.delta_1m = options.longs === String ? $util.Long.prototype.toString.call(message.delta_1m) : options.longs === Number ? new $util.LongBits(message.delta_1m.low >>> 0, message.delta_1m.high >>> 0).toNumber() : message.delta_1m;
            if (message.delta_5m != null && message.hasOwnProperty("delta_5m"))
                if (typeof message.delta_5m === "number")
                    object.delta_5m = options.longs === String ? String(message.delta_5m) : message.delta_5m;
                else
                    object.delta_5m = options.longs === String ? $util.Long.prototype.toString.call(message.delta_5m) : options.longs === Number ? new $util.LongBits(message.delta_5m.low >>> 0, message.delta_5m.high >>> 0).toNumber() : message.delta_5m;
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (typeof message.timestampMs === "number")
                    object.timestampMs = options.longs === String ? String(message.timestampMs) : message.timestampMs;
                else
                    object.timestampMs = options.longs === String ? $util.Long.prototype.toString.call(message.timestampMs) : options.longs === Number ? new $util.LongBits(message.timestampMs.low >>> 0, message.timestampMs.high >>> 0).toNumber() : message.timestampMs;
            return object;
        };

        /**
         * Converts this Cvd to JSON.
         * @function toJSON
         * @memberof market.Cvd
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        Cvd.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for Cvd
         * @function getTypeUrl
         * @memberof market.Cvd
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        Cvd.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/market.Cvd";
        };

        return Cvd;
    })();

    market.Sweep = (function() {

        /**
         * Properties of a Sweep.
         * @memberof market
         * @interface ISweep
         * @property {number|null} [price] Sweep price
         * @property {number|Long|null} [size] Sweep size
         * @property {market.TradeSide|null} [side] Sweep side
         * @property {number|null} [levelsHit] Sweep levelsHit
         * @property {number|Long|null} [timestampMs] Sweep timestampMs
         */

        /**
         * Constructs a new Sweep.
         * @memberof market
         * @classdesc Represents a Sweep.
         * @implements ISweep
         * @constructor
         * @param {market.ISweep=} [properties] Properties to set
         */
        function Sweep(properties) {
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * Sweep price.
         * @member {number} price
         * @memberof market.Sweep
         * @instance
         */
        Sweep.prototype.price = 0;

        /**
         * Sweep size.
         * @member {number|Long} size
         * @memberof market.Sweep
         * @instance
         */
        Sweep.prototype.size = $util.Long ? $util.Long.fromBits(0,0,true) : 0;

        /**
         * Sweep side.
         * @member {market.TradeSide} side
         * @memberof market.Sweep
         * @instance
         */
        Sweep.prototype.side = 0;

        /**
         * Sweep levelsHit.
         * @member {number} levelsHit
         * @memberof market.Sweep
         * @instance
         */
        Sweep.prototype.levelsHit = 0;

        /**
         * Sweep timestampMs.
         * @member {number|Long} timestampMs
         * @memberof market.Sweep
         * @instance
         */
        Sweep.prototype.timestampMs = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * Creates a new Sweep instance using the specified properties.
         * @function create
         * @memberof market.Sweep
         * @static
         * @param {market.ISweep=} [properties] Properties to set
         * @returns {market.Sweep} Sweep instance
         */
        Sweep.create = function create(properties) {
            return new Sweep(properties);
        };

        /**
         * Encodes the specified Sweep message. Does not implicitly {@link market.Sweep.verify|verify} messages.
         * @function encode
         * @memberof market.Sweep
         * @static
         * @param {market.ISweep} message Sweep message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Sweep.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.price != null && Object.hasOwnProperty.call(message, "price"))
                writer.uint32(/* id 1, wireType 1 =*/9).double(message.price);
            if (message.size != null && Object.hasOwnProperty.call(message, "size"))
                writer.uint32(/* id 2, wireType 0 =*/16).uint64(message.size);
            if (message.side != null && Object.hasOwnProperty.call(message, "side"))
                writer.uint32(/* id 3, wireType 0 =*/24).int32(message.side);
            if (message.levelsHit != null && Object.hasOwnProperty.call(message, "levelsHit"))
                writer.uint32(/* id 4, wireType 0 =*/32).uint32(message.levelsHit);
            if (message.timestampMs != null && Object.hasOwnProperty.call(message, "timestampMs"))
                writer.uint32(/* id 5, wireType 0 =*/40).int64(message.timestampMs);
            return writer;
        };

        /**
         * Encodes the specified Sweep message, length delimited. Does not implicitly {@link market.Sweep.verify|verify} messages.
         * @function encodeDelimited
         * @memberof market.Sweep
         * @static
         * @param {market.ISweep} message Sweep message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Sweep.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a Sweep message from the specified reader or buffer.
         * @function decode
         * @memberof market.Sweep
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {market.Sweep} Sweep
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Sweep.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.market.Sweep();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.price = reader.double();
                        break;
                    }
                case 2: {
                        message.size = reader.uint64();
                        break;
                    }
                case 3: {
                        message.side = reader.int32();
                        break;
                    }
                case 4: {
                        message.levelsHit = reader.uint32();
                        break;
                    }
                case 5: {
                        message.timestampMs = reader.int64();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a Sweep message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof market.Sweep
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {market.Sweep} Sweep
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Sweep.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a Sweep message.
         * @function verify
         * @memberof market.Sweep
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        Sweep.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.price != null && message.hasOwnProperty("price"))
                if (typeof message.price !== "number")
                    return "price: number expected";
            if (message.size != null && message.hasOwnProperty("size"))
                if (!$util.isInteger(message.size) && !(message.size && $util.isInteger(message.size.low) && $util.isInteger(message.size.high)))
                    return "size: integer|Long expected";
            if (message.side != null && message.hasOwnProperty("side"))
                switch (message.side) {
                default:
                    return "side: enum value expected";
                case 0:
                case 1:
                case 2:
                    break;
                }
            if (message.levelsHit != null && message.hasOwnProperty("levelsHit"))
                if (!$util.isInteger(message.levelsHit))
                    return "levelsHit: integer expected";
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (!$util.isInteger(message.timestampMs) && !(message.timestampMs && $util.isInteger(message.timestampMs.low) && $util.isInteger(message.timestampMs.high)))
                    return "timestampMs: integer|Long expected";
            return null;
        };

        /**
         * Creates a Sweep message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof market.Sweep
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {market.Sweep} Sweep
         */
        Sweep.fromObject = function fromObject(object) {
            if (object instanceof $root.market.Sweep)
                return object;
            let message = new $root.market.Sweep();
            if (object.price != null)
                message.price = Number(object.price);
            if (object.size != null)
                if ($util.Long)
                    (message.size = $util.Long.fromValue(object.size)).unsigned = true;
                else if (typeof object.size === "string")
                    message.size = parseInt(object.size, 10);
                else if (typeof object.size === "number")
                    message.size = object.size;
                else if (typeof object.size === "object")
                    message.size = new $util.LongBits(object.size.low >>> 0, object.size.high >>> 0).toNumber(true);
            switch (object.side) {
            default:
                if (typeof object.side === "number") {
                    message.side = object.side;
                    break;
                }
                break;
            case "SIDE_UNKNOWN":
            case 0:
                message.side = 0;
                break;
            case "SIDE_BUY":
            case 1:
                message.side = 1;
                break;
            case "SIDE_SELL":
            case 2:
                message.side = 2;
                break;
            }
            if (object.levelsHit != null)
                message.levelsHit = object.levelsHit >>> 0;
            if (object.timestampMs != null)
                if ($util.Long)
                    (message.timestampMs = $util.Long.fromValue(object.timestampMs)).unsigned = false;
                else if (typeof object.timestampMs === "string")
                    message.timestampMs = parseInt(object.timestampMs, 10);
                else if (typeof object.timestampMs === "number")
                    message.timestampMs = object.timestampMs;
                else if (typeof object.timestampMs === "object")
                    message.timestampMs = new $util.LongBits(object.timestampMs.low >>> 0, object.timestampMs.high >>> 0).toNumber();
            return message;
        };

        /**
         * Creates a plain object from a Sweep message. Also converts values to other types if specified.
         * @function toObject
         * @memberof market.Sweep
         * @static
         * @param {market.Sweep} message Sweep
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        Sweep.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.defaults) {
                object.price = 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, true);
                    object.size = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.size = options.longs === String ? "0" : 0;
                object.side = options.enums === String ? "SIDE_UNKNOWN" : 0;
                object.levelsHit = 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.timestampMs = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.timestampMs = options.longs === String ? "0" : 0;
            }
            if (message.price != null && message.hasOwnProperty("price"))
                object.price = options.json && !isFinite(message.price) ? String(message.price) : message.price;
            if (message.size != null && message.hasOwnProperty("size"))
                if (typeof message.size === "number")
                    object.size = options.longs === String ? String(message.size) : message.size;
                else
                    object.size = options.longs === String ? $util.Long.prototype.toString.call(message.size) : options.longs === Number ? new $util.LongBits(message.size.low >>> 0, message.size.high >>> 0).toNumber(true) : message.size;
            if (message.side != null && message.hasOwnProperty("side"))
                object.side = options.enums === String ? $root.market.TradeSide[message.side] === undefined ? message.side : $root.market.TradeSide[message.side] : message.side;
            if (message.levelsHit != null && message.hasOwnProperty("levelsHit"))
                object.levelsHit = message.levelsHit;
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (typeof message.timestampMs === "number")
                    object.timestampMs = options.longs === String ? String(message.timestampMs) : message.timestampMs;
                else
                    object.timestampMs = options.longs === String ? $util.Long.prototype.toString.call(message.timestampMs) : options.longs === Number ? new $util.LongBits(message.timestampMs.low >>> 0, message.timestampMs.high >>> 0).toNumber() : message.timestampMs;
            return object;
        };

        /**
         * Converts this Sweep to JSON.
         * @function toJSON
         * @memberof market.Sweep
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        Sweep.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for Sweep
         * @function getTypeUrl
         * @memberof market.Sweep
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        Sweep.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/market.Sweep";
        };

        return Sweep;
    })();

    market.Imbalance = (function() {

        /**
         * Properties of an Imbalance.
         * @memberof market
         * @interface IImbalance
         * @property {number|null} [price] Imbalance price
         * @property {market.TradeSide|null} [side] Imbalance side
         * @property {number|null} [ratio] Imbalance ratio
         * @property {number|null} [stacked] Imbalance stacked
         * @property {number|Long|null} [timestampMs] Imbalance timestampMs
         */

        /**
         * Constructs a new Imbalance.
         * @memberof market
         * @classdesc Represents an Imbalance.
         * @implements IImbalance
         * @constructor
         * @param {market.IImbalance=} [properties] Properties to set
         */
        function Imbalance(properties) {
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * Imbalance price.
         * @member {number} price
         * @memberof market.Imbalance
         * @instance
         */
        Imbalance.prototype.price = 0;

        /**
         * Imbalance side.
         * @member {market.TradeSide} side
         * @memberof market.Imbalance
         * @instance
         */
        Imbalance.prototype.side = 0;

        /**
         * Imbalance ratio.
         * @member {number} ratio
         * @memberof market.Imbalance
         * @instance
         */
        Imbalance.prototype.ratio = 0;

        /**
         * Imbalance stacked.
         * @member {number} stacked
         * @memberof market.Imbalance
         * @instance
         */
        Imbalance.prototype.stacked = 0;

        /**
         * Imbalance timestampMs.
         * @member {number|Long} timestampMs
         * @memberof market.Imbalance
         * @instance
         */
        Imbalance.prototype.timestampMs = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * Creates a new Imbalance instance using the specified properties.
         * @function create
         * @memberof market.Imbalance
         * @static
         * @param {market.IImbalance=} [properties] Properties to set
         * @returns {market.Imbalance} Imbalance instance
         */
        Imbalance.create = function create(properties) {
            return new Imbalance(properties);
        };

        /**
         * Encodes the specified Imbalance message. Does not implicitly {@link market.Imbalance.verify|verify} messages.
         * @function encode
         * @memberof market.Imbalance
         * @static
         * @param {market.IImbalance} message Imbalance message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Imbalance.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.price != null && Object.hasOwnProperty.call(message, "price"))
                writer.uint32(/* id 1, wireType 1 =*/9).double(message.price);
            if (message.side != null && Object.hasOwnProperty.call(message, "side"))
                writer.uint32(/* id 2, wireType 0 =*/16).int32(message.side);
            if (message.ratio != null && Object.hasOwnProperty.call(message, "ratio"))
                writer.uint32(/* id 3, wireType 1 =*/25).double(message.ratio);
            if (message.stacked != null && Object.hasOwnProperty.call(message, "stacked"))
                writer.uint32(/* id 4, wireType 0 =*/32).uint32(message.stacked);
            if (message.timestampMs != null && Object.hasOwnProperty.call(message, "timestampMs"))
                writer.uint32(/* id 5, wireType 0 =*/40).int64(message.timestampMs);
            return writer;
        };

        /**
         * Encodes the specified Imbalance message, length delimited. Does not implicitly {@link market.Imbalance.verify|verify} messages.
         * @function encodeDelimited
         * @memberof market.Imbalance
         * @static
         * @param {market.IImbalance} message Imbalance message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Imbalance.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes an Imbalance message from the specified reader or buffer.
         * @function decode
         * @memberof market.Imbalance
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {market.Imbalance} Imbalance
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Imbalance.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.market.Imbalance();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.price = reader.double();
                        break;
                    }
                case 2: {
                        message.side = reader.int32();
                        break;
                    }
                case 3: {
                        message.ratio = reader.double();
                        break;
                    }
                case 4: {
                        message.stacked = reader.uint32();
                        break;
                    }
                case 5: {
                        message.timestampMs = reader.int64();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes an Imbalance message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof market.Imbalance
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {market.Imbalance} Imbalance
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Imbalance.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies an Imbalance message.
         * @function verify
         * @memberof market.Imbalance
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        Imbalance.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.price != null && message.hasOwnProperty("price"))
                if (typeof message.price !== "number")
                    return "price: number expected";
            if (message.side != null && message.hasOwnProperty("side"))
                switch (message.side) {
                default:
                    return "side: enum value expected";
                case 0:
                case 1:
                case 2:
                    break;
                }
            if (message.ratio != null && message.hasOwnProperty("ratio"))
                if (typeof message.ratio !== "number")
                    return "ratio: number expected";
            if (message.stacked != null && message.hasOwnProperty("stacked"))
                if (!$util.isInteger(message.stacked))
                    return "stacked: integer expected";
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (!$util.isInteger(message.timestampMs) && !(message.timestampMs && $util.isInteger(message.timestampMs.low) && $util.isInteger(message.timestampMs.high)))
                    return "timestampMs: integer|Long expected";
            return null;
        };

        /**
         * Creates an Imbalance message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof market.Imbalance
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {market.Imbalance} Imbalance
         */
        Imbalance.fromObject = function fromObject(object) {
            if (object instanceof $root.market.Imbalance)
                return object;
            let message = new $root.market.Imbalance();
            if (object.price != null)
                message.price = Number(object.price);
            switch (object.side) {
            default:
                if (typeof object.side === "number") {
                    message.side = object.side;
                    break;
                }
                break;
            case "SIDE_UNKNOWN":
            case 0:
                message.side = 0;
                break;
            case "SIDE_BUY":
            case 1:
                message.side = 1;
                break;
            case "SIDE_SELL":
            case 2:
                message.side = 2;
                break;
            }
            if (object.ratio != null)
                message.ratio = Number(object.ratio);
            if (object.stacked != null)
                message.stacked = object.stacked >>> 0;
            if (object.timestampMs != null)
                if ($util.Long)
                    (message.timestampMs = $util.Long.fromValue(object.timestampMs)).unsigned = false;
                else if (typeof object.timestampMs === "string")
                    message.timestampMs = parseInt(object.timestampMs, 10);
                else if (typeof object.timestampMs === "number")
                    message.timestampMs = object.timestampMs;
                else if (typeof object.timestampMs === "object")
                    message.timestampMs = new $util.LongBits(object.timestampMs.low >>> 0, object.timestampMs.high >>> 0).toNumber();
            return message;
        };

        /**
         * Creates a plain object from an Imbalance message. Also converts values to other types if specified.
         * @function toObject
         * @memberof market.Imbalance
         * @static
         * @param {market.Imbalance} message Imbalance
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        Imbalance.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.defaults) {
                object.price = 0;
                object.side = options.enums === String ? "SIDE_UNKNOWN" : 0;
                object.ratio = 0;
                object.stacked = 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.timestampMs = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.timestampMs = options.longs === String ? "0" : 0;
            }
            if (message.price != null && message.hasOwnProperty("price"))
                object.price = options.json && !isFinite(message.price) ? String(message.price) : message.price;
            if (message.side != null && message.hasOwnProperty("side"))
                object.side = options.enums === String ? $root.market.TradeSide[message.side] === undefined ? message.side : $root.market.TradeSide[message.side] : message.side;
            if (message.ratio != null && message.hasOwnProperty("ratio"))
                object.ratio = options.json && !isFinite(message.ratio) ? String(message.ratio) : message.ratio;
            if (message.stacked != null && message.hasOwnProperty("stacked"))
                object.stacked = message.stacked;
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (typeof message.timestampMs === "number")
                    object.timestampMs = options.longs === String ? String(message.timestampMs) : message.timestampMs;
                else
                    object.timestampMs = options.longs === String ? $util.Long.prototype.toString.call(message.timestampMs) : options.longs === Number ? new $util.LongBits(message.timestampMs.low >>> 0, message.timestampMs.high >>> 0).toNumber() : message.timestampMs;
            return object;
        };

        /**
         * Converts this Imbalance to JSON.
         * @function toJSON
         * @memberof market.Imbalance
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        Imbalance.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for Imbalance
         * @function getTypeUrl
         * @memberof market.Imbalance
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        Imbalance.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/market.Imbalance";
        };

        return Imbalance;
    })();

    market.Absorption = (function() {

        /**
         * Properties of an Absorption.
         * @memberof market
         * @interface IAbsorption
         * @property {number|null} [price] Absorption price
         * @property {number|Long|null} [volume] Absorption volume
         * @property {market.TradeSide|null} [side] Absorption side
         * @property {boolean|null} [held] Absorption held
         * @property {number|Long|null} [timestampMs] Absorption timestampMs
         */

        /**
         * Constructs a new Absorption.
         * @memberof market
         * @classdesc Represents an Absorption.
         * @implements IAbsorption
         * @constructor
         * @param {market.IAbsorption=} [properties] Properties to set
         */
        function Absorption(properties) {
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * Absorption price.
         * @member {number} price
         * @memberof market.Absorption
         * @instance
         */
        Absorption.prototype.price = 0;

        /**
         * Absorption volume.
         * @member {number|Long} volume
         * @memberof market.Absorption
         * @instance
         */
        Absorption.prototype.volume = $util.Long ? $util.Long.fromBits(0,0,true) : 0;

        /**
         * Absorption side.
         * @member {market.TradeSide} side
         * @memberof market.Absorption
         * @instance
         */
        Absorption.prototype.side = 0;

        /**
         * Absorption held.
         * @member {boolean} held
         * @memberof market.Absorption
         * @instance
         */
        Absorption.prototype.held = false;

        /**
         * Absorption timestampMs.
         * @member {number|Long} timestampMs
         * @memberof market.Absorption
         * @instance
         */
        Absorption.prototype.timestampMs = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * Creates a new Absorption instance using the specified properties.
         * @function create
         * @memberof market.Absorption
         * @static
         * @param {market.IAbsorption=} [properties] Properties to set
         * @returns {market.Absorption} Absorption instance
         */
        Absorption.create = function create(properties) {
            return new Absorption(properties);
        };

        /**
         * Encodes the specified Absorption message. Does not implicitly {@link market.Absorption.verify|verify} messages.
         * @function encode
         * @memberof market.Absorption
         * @static
         * @param {market.IAbsorption} message Absorption message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Absorption.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.price != null && Object.hasOwnProperty.call(message, "price"))
                writer.uint32(/* id 1, wireType 1 =*/9).double(message.price);
            if (message.volume != null && Object.hasOwnProperty.call(message, "volume"))
                writer.uint32(/* id 2, wireType 0 =*/16).uint64(message.volume);
            if (message.side != null && Object.hasOwnProperty.call(message, "side"))
                writer.uint32(/* id 3, wireType 0 =*/24).int32(message.side);
            if (message.held != null && Object.hasOwnProperty.call(message, "held"))
                writer.uint32(/* id 4, wireType 0 =*/32).bool(message.held);
            if (message.timestampMs != null && Object.hasOwnProperty.call(message, "timestampMs"))
                writer.uint32(/* id 5, wireType 0 =*/40).int64(message.timestampMs);
            return writer;
        };

        /**
         * Encodes the specified Absorption message, length delimited. Does not implicitly {@link market.Absorption.verify|verify} messages.
         * @function encodeDelimited
         * @memberof market.Absorption
         * @static
         * @param {market.IAbsorption} message Absorption message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Absorption.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes an Absorption message from the specified reader or buffer.
         * @function decode
         * @memberof market.Absorption
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {market.Absorption} Absorption
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Absorption.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.market.Absorption();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.price = reader.double();
                        break;
                    }
                case 2: {
                        message.volume = reader.uint64();
                        break;
                    }
                case 3: {
                        message.side = reader.int32();
                        break;
                    }
                case 4: {
                        message.held = reader.bool();
                        break;
                    }
                case 5: {
                        message.timestampMs = reader.int64();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes an Absorption message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof market.Absorption
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {market.Absorption} Absorption
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Absorption.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies an Absorption message.
         * @function verify
         * @memberof market.Absorption
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        Absorption.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.price != null && message.hasOwnProperty("price"))
                if (typeof message.price !== "number")
                    return "price: number expected";
            if (message.volume != null && message.hasOwnProperty("volume"))
                if (!$util.isInteger(message.volume) && !(message.volume && $util.isInteger(message.volume.low) && $util.isInteger(message.volume.high)))
                    return "volume: integer|Long expected";
            if (message.side != null && message.hasOwnProperty("side"))
                switch (message.side) {
                default:
                    return "side: enum value expected";
                case 0:
                case 1:
                case 2:
                    break;
                }
            if (message.held != null && message.hasOwnProperty("held"))
                if (typeof message.held !== "boolean")
                    return "held: boolean expected";
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (!$util.isInteger(message.timestampMs) && !(message.timestampMs && $util.isInteger(message.timestampMs.low) && $util.isInteger(message.timestampMs.high)))
                    return "timestampMs: integer|Long expected";
            return null;
        };

        /**
         * Creates an Absorption message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof market.Absorption
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {market.Absorption} Absorption
         */
        Absorption.fromObject = function fromObject(object) {
            if (object instanceof $root.market.Absorption)
                return object;
            let message = new $root.market.Absorption();
            if (object.price != null)
                message.price = Number(object.price);
            if (object.volume != null)
                if ($util.Long)
                    (message.volume = $util.Long.fromValue(object.volume)).unsigned = true;
                else if (typeof object.volume === "string")
                    message.volume = parseInt(object.volume, 10);
                else if (typeof object.volume === "number")
                    message.volume = object.volume;
                else if (typeof object.volume === "object")
                    message.volume = new $util.LongBits(object.volume.low >>> 0, object.volume.high >>> 0).toNumber(true);
            switch (object.side) {
            default:
                if (typeof object.side === "number") {
                    message.side = object.side;
                    break;
                }
                break;
            case "SIDE_UNKNOWN":
            case 0:
                message.side = 0;
                break;
            case "SIDE_BUY":
            case 1:
                message.side = 1;
                break;
            case "SIDE_SELL":
            case 2:
                message.side = 2;
                break;
            }
            if (object.held != null)
                message.held = Boolean(object.held);
            if (object.timestampMs != null)
                if ($util.Long)
                    (message.timestampMs = $util.Long.fromValue(object.timestampMs)).unsigned = false;
                else if (typeof object.timestampMs === "string")
                    message.timestampMs = parseInt(object.timestampMs, 10);
                else if (typeof object.timestampMs === "number")
                    message.timestampMs = object.timestampMs;
                else if (typeof object.timestampMs === "object")
                    message.timestampMs = new $util.LongBits(object.timestampMs.low >>> 0, object.timestampMs.high >>> 0).toNumber();
            return message;
        };

        /**
         * Creates a plain object from an Absorption message. Also converts values to other types if specified.
         * @function toObject
         * @memberof market.Absorption
         * @static
         * @param {market.Absorption} message Absorption
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        Absorption.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.defaults) {
                object.price = 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, true);
                    object.volume = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.volume = options.longs === String ? "0" : 0;
                object.side = options.enums === String ? "SIDE_UNKNOWN" : 0;
                object.held = false;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.timestampMs = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.timestampMs = options.longs === String ? "0" : 0;
            }
            if (message.price != null && message.hasOwnProperty("price"))
                object.price = options.json && !isFinite(message.price) ? String(message.price) : message.price;
            if (message.volume != null && message.hasOwnProperty("volume"))
                if (typeof message.volume === "number")
                    object.volume = options.longs === String ? String(message.volume) : message.volume;
                else
                    object.volume = options.longs === String ? $util.Long.prototype.toString.call(message.volume) : options.longs === Number ? new $util.LongBits(message.volume.low >>> 0, message.volume.high >>> 0).toNumber(true) : message.volume;
            if (message.side != null && message.hasOwnProperty("side"))
                object.side = options.enums === String ? $root.market.TradeSide[message.side] === undefined ? message.side : $root.market.TradeSide[message.side] : message.side;
            if (message.held != null && message.hasOwnProperty("held"))
                object.held = message.held;
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (typeof message.timestampMs === "number")
                    object.timestampMs = options.longs === String ? String(message.timestampMs) : message.timestampMs;
                else
                    object.timestampMs = options.longs === String ? $util.Long.prototype.toString.call(message.timestampMs) : options.longs === Number ? new $util.LongBits(message.timestampMs.low >>> 0, message.timestampMs.high >>> 0).toNumber() : message.timestampMs;
            return object;
        };

        /**
         * Converts this Absorption to JSON.
         * @function toJSON
         * @memberof market.Absorption
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        Absorption.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for Absorption
         * @function getTypeUrl
         * @memberof market.Absorption
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        Absorption.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/market.Absorption";
        };

        return Absorption;
    })();

    market.DeltaFlip = (function() {

        /**
         * Properties of a DeltaFlip.
         * @memberof market
         * @interface IDeltaFlip
         * @property {market.TradeSide|null} [from] DeltaFlip from
         * @property {market.TradeSide|null} [to] DeltaFlip to
         * @property {number|Long|null} [cvdAtFlip] DeltaFlip cvdAtFlip
         * @property {number|Long|null} [timestampMs] DeltaFlip timestampMs
         */

        /**
         * Constructs a new DeltaFlip.
         * @memberof market
         * @classdesc Represents a DeltaFlip.
         * @implements IDeltaFlip
         * @constructor
         * @param {market.IDeltaFlip=} [properties] Properties to set
         */
        function DeltaFlip(properties) {
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * DeltaFlip from.
         * @member {market.TradeSide} from
         * @memberof market.DeltaFlip
         * @instance
         */
        DeltaFlip.prototype.from = 0;

        /**
         * DeltaFlip to.
         * @member {market.TradeSide} to
         * @memberof market.DeltaFlip
         * @instance
         */
        DeltaFlip.prototype.to = 0;

        /**
         * DeltaFlip cvdAtFlip.
         * @member {number|Long} cvdAtFlip
         * @memberof market.DeltaFlip
         * @instance
         */
        DeltaFlip.prototype.cvdAtFlip = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * DeltaFlip timestampMs.
         * @member {number|Long} timestampMs
         * @memberof market.DeltaFlip
         * @instance
         */
        DeltaFlip.prototype.timestampMs = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * Creates a new DeltaFlip instance using the specified properties.
         * @function create
         * @memberof market.DeltaFlip
         * @static
         * @param {market.IDeltaFlip=} [properties] Properties to set
         * @returns {market.DeltaFlip} DeltaFlip instance
         */
        DeltaFlip.create = function create(properties) {
            return new DeltaFlip(properties);
        };

        /**
         * Encodes the specified DeltaFlip message. Does not implicitly {@link market.DeltaFlip.verify|verify} messages.
         * @function encode
         * @memberof market.DeltaFlip
         * @static
         * @param {market.IDeltaFlip} message DeltaFlip message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        DeltaFlip.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.from != null && Object.hasOwnProperty.call(message, "from"))
                writer.uint32(/* id 1, wireType 0 =*/8).int32(message.from);
            if (message.to != null && Object.hasOwnProperty.call(message, "to"))
                writer.uint32(/* id 2, wireType 0 =*/16).int32(message.to);
            if (message.cvdAtFlip != null && Object.hasOwnProperty.call(message, "cvdAtFlip"))
                writer.uint32(/* id 3, wireType 0 =*/24).int64(message.cvdAtFlip);
            if (message.timestampMs != null && Object.hasOwnProperty.call(message, "timestampMs"))
                writer.uint32(/* id 4, wireType 0 =*/32).int64(message.timestampMs);
            return writer;
        };

        /**
         * Encodes the specified DeltaFlip message, length delimited. Does not implicitly {@link market.DeltaFlip.verify|verify} messages.
         * @function encodeDelimited
         * @memberof market.DeltaFlip
         * @static
         * @param {market.IDeltaFlip} message DeltaFlip message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        DeltaFlip.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a DeltaFlip message from the specified reader or buffer.
         * @function decode
         * @memberof market.DeltaFlip
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {market.DeltaFlip} DeltaFlip
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        DeltaFlip.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.market.DeltaFlip();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.from = reader.int32();
                        break;
                    }
                case 2: {
                        message.to = reader.int32();
                        break;
                    }
                case 3: {
                        message.cvdAtFlip = reader.int64();
                        break;
                    }
                case 4: {
                        message.timestampMs = reader.int64();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a DeltaFlip message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof market.DeltaFlip
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {market.DeltaFlip} DeltaFlip
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        DeltaFlip.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a DeltaFlip message.
         * @function verify
         * @memberof market.DeltaFlip
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        DeltaFlip.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.from != null && message.hasOwnProperty("from"))
                switch (message.from) {
                default:
                    return "from: enum value expected";
                case 0:
                case 1:
                case 2:
                    break;
                }
            if (message.to != null && message.hasOwnProperty("to"))
                switch (message.to) {
                default:
                    return "to: enum value expected";
                case 0:
                case 1:
                case 2:
                    break;
                }
            if (message.cvdAtFlip != null && message.hasOwnProperty("cvdAtFlip"))
                if (!$util.isInteger(message.cvdAtFlip) && !(message.cvdAtFlip && $util.isInteger(message.cvdAtFlip.low) && $util.isInteger(message.cvdAtFlip.high)))
                    return "cvdAtFlip: integer|Long expected";
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (!$util.isInteger(message.timestampMs) && !(message.timestampMs && $util.isInteger(message.timestampMs.low) && $util.isInteger(message.timestampMs.high)))
                    return "timestampMs: integer|Long expected";
            return null;
        };

        /**
         * Creates a DeltaFlip message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof market.DeltaFlip
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {market.DeltaFlip} DeltaFlip
         */
        DeltaFlip.fromObject = function fromObject(object) {
            if (object instanceof $root.market.DeltaFlip)
                return object;
            let message = new $root.market.DeltaFlip();
            switch (object.from) {
            default:
                if (typeof object.from === "number") {
                    message.from = object.from;
                    break;
                }
                break;
            case "SIDE_UNKNOWN":
            case 0:
                message.from = 0;
                break;
            case "SIDE_BUY":
            case 1:
                message.from = 1;
                break;
            case "SIDE_SELL":
            case 2:
                message.from = 2;
                break;
            }
            switch (object.to) {
            default:
                if (typeof object.to === "number") {
                    message.to = object.to;
                    break;
                }
                break;
            case "SIDE_UNKNOWN":
            case 0:
                message.to = 0;
                break;
            case "SIDE_BUY":
            case 1:
                message.to = 1;
                break;
            case "SIDE_SELL":
            case 2:
                message.to = 2;
                break;
            }
            if (object.cvdAtFlip != null)
                if ($util.Long)
                    (message.cvdAtFlip = $util.Long.fromValue(object.cvdAtFlip)).unsigned = false;
                else if (typeof object.cvdAtFlip === "string")
                    message.cvdAtFlip = parseInt(object.cvdAtFlip, 10);
                else if (typeof object.cvdAtFlip === "number")
                    message.cvdAtFlip = object.cvdAtFlip;
                else if (typeof object.cvdAtFlip === "object")
                    message.cvdAtFlip = new $util.LongBits(object.cvdAtFlip.low >>> 0, object.cvdAtFlip.high >>> 0).toNumber();
            if (object.timestampMs != null)
                if ($util.Long)
                    (message.timestampMs = $util.Long.fromValue(object.timestampMs)).unsigned = false;
                else if (typeof object.timestampMs === "string")
                    message.timestampMs = parseInt(object.timestampMs, 10);
                else if (typeof object.timestampMs === "number")
                    message.timestampMs = object.timestampMs;
                else if (typeof object.timestampMs === "object")
                    message.timestampMs = new $util.LongBits(object.timestampMs.low >>> 0, object.timestampMs.high >>> 0).toNumber();
            return message;
        };

        /**
         * Creates a plain object from a DeltaFlip message. Also converts values to other types if specified.
         * @function toObject
         * @memberof market.DeltaFlip
         * @static
         * @param {market.DeltaFlip} message DeltaFlip
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        DeltaFlip.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.defaults) {
                object.from = options.enums === String ? "SIDE_UNKNOWN" : 0;
                object.to = options.enums === String ? "SIDE_UNKNOWN" : 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.cvdAtFlip = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.cvdAtFlip = options.longs === String ? "0" : 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.timestampMs = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.timestampMs = options.longs === String ? "0" : 0;
            }
            if (message.from != null && message.hasOwnProperty("from"))
                object.from = options.enums === String ? $root.market.TradeSide[message.from] === undefined ? message.from : $root.market.TradeSide[message.from] : message.from;
            if (message.to != null && message.hasOwnProperty("to"))
                object.to = options.enums === String ? $root.market.TradeSide[message.to] === undefined ? message.to : $root.market.TradeSide[message.to] : message.to;
            if (message.cvdAtFlip != null && message.hasOwnProperty("cvdAtFlip"))
                if (typeof message.cvdAtFlip === "number")
                    object.cvdAtFlip = options.longs === String ? String(message.cvdAtFlip) : message.cvdAtFlip;
                else
                    object.cvdAtFlip = options.longs === String ? $util.Long.prototype.toString.call(message.cvdAtFlip) : options.longs === Number ? new $util.LongBits(message.cvdAtFlip.low >>> 0, message.cvdAtFlip.high >>> 0).toNumber() : message.cvdAtFlip;
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (typeof message.timestampMs === "number")
                    object.timestampMs = options.longs === String ? String(message.timestampMs) : message.timestampMs;
                else
                    object.timestampMs = options.longs === String ? $util.Long.prototype.toString.call(message.timestampMs) : options.longs === Number ? new $util.LongBits(message.timestampMs.low >>> 0, message.timestampMs.high >>> 0).toNumber() : message.timestampMs;
            return object;
        };

        /**
         * Converts this DeltaFlip to JSON.
         * @function toJSON
         * @memberof market.DeltaFlip
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        DeltaFlip.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for DeltaFlip
         * @function getTypeUrl
         * @memberof market.DeltaFlip
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        DeltaFlip.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/market.DeltaFlip";
        };

        return DeltaFlip;
    })();

    market.LargeTrade = (function() {

        /**
         * Properties of a LargeTrade.
         * @memberof market
         * @interface ILargeTrade
         * @property {number|null} [price] LargeTrade price
         * @property {number|Long|null} [size] LargeTrade size
         * @property {market.TradeSide|null} [side] LargeTrade side
         * @property {number|Long|null} [timestampMs] LargeTrade timestampMs
         */

        /**
         * Constructs a new LargeTrade.
         * @memberof market
         * @classdesc Represents a LargeTrade.
         * @implements ILargeTrade
         * @constructor
         * @param {market.ILargeTrade=} [properties] Properties to set
         */
        function LargeTrade(properties) {
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * LargeTrade price.
         * @member {number} price
         * @memberof market.LargeTrade
         * @instance
         */
        LargeTrade.prototype.price = 0;

        /**
         * LargeTrade size.
         * @member {number|Long} size
         * @memberof market.LargeTrade
         * @instance
         */
        LargeTrade.prototype.size = $util.Long ? $util.Long.fromBits(0,0,true) : 0;

        /**
         * LargeTrade side.
         * @member {market.TradeSide} side
         * @memberof market.LargeTrade
         * @instance
         */
        LargeTrade.prototype.side = 0;

        /**
         * LargeTrade timestampMs.
         * @member {number|Long} timestampMs
         * @memberof market.LargeTrade
         * @instance
         */
        LargeTrade.prototype.timestampMs = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * Creates a new LargeTrade instance using the specified properties.
         * @function create
         * @memberof market.LargeTrade
         * @static
         * @param {market.ILargeTrade=} [properties] Properties to set
         * @returns {market.LargeTrade} LargeTrade instance
         */
        LargeTrade.create = function create(properties) {
            return new LargeTrade(properties);
        };

        /**
         * Encodes the specified LargeTrade message. Does not implicitly {@link market.LargeTrade.verify|verify} messages.
         * @function encode
         * @memberof market.LargeTrade
         * @static
         * @param {market.ILargeTrade} message LargeTrade message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        LargeTrade.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.price != null && Object.hasOwnProperty.call(message, "price"))
                writer.uint32(/* id 1, wireType 1 =*/9).double(message.price);
            if (message.size != null && Object.hasOwnProperty.call(message, "size"))
                writer.uint32(/* id 2, wireType 0 =*/16).uint64(message.size);
            if (message.side != null && Object.hasOwnProperty.call(message, "side"))
                writer.uint32(/* id 3, wireType 0 =*/24).int32(message.side);
            if (message.timestampMs != null && Object.hasOwnProperty.call(message, "timestampMs"))
                writer.uint32(/* id 4, wireType 0 =*/32).int64(message.timestampMs);
            return writer;
        };

        /**
         * Encodes the specified LargeTrade message, length delimited. Does not implicitly {@link market.LargeTrade.verify|verify} messages.
         * @function encodeDelimited
         * @memberof market.LargeTrade
         * @static
         * @param {market.ILargeTrade} message LargeTrade message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        LargeTrade.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a LargeTrade message from the specified reader or buffer.
         * @function decode
         * @memberof market.LargeTrade
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {market.LargeTrade} LargeTrade
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        LargeTrade.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.market.LargeTrade();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.price = reader.double();
                        break;
                    }
                case 2: {
                        message.size = reader.uint64();
                        break;
                    }
                case 3: {
                        message.side = reader.int32();
                        break;
                    }
                case 4: {
                        message.timestampMs = reader.int64();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a LargeTrade message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof market.LargeTrade
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {market.LargeTrade} LargeTrade
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        LargeTrade.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a LargeTrade message.
         * @function verify
         * @memberof market.LargeTrade
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        LargeTrade.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.price != null && message.hasOwnProperty("price"))
                if (typeof message.price !== "number")
                    return "price: number expected";
            if (message.size != null && message.hasOwnProperty("size"))
                if (!$util.isInteger(message.size) && !(message.size && $util.isInteger(message.size.low) && $util.isInteger(message.size.high)))
                    return "size: integer|Long expected";
            if (message.side != null && message.hasOwnProperty("side"))
                switch (message.side) {
                default:
                    return "side: enum value expected";
                case 0:
                case 1:
                case 2:
                    break;
                }
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (!$util.isInteger(message.timestampMs) && !(message.timestampMs && $util.isInteger(message.timestampMs.low) && $util.isInteger(message.timestampMs.high)))
                    return "timestampMs: integer|Long expected";
            return null;
        };

        /**
         * Creates a LargeTrade message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof market.LargeTrade
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {market.LargeTrade} LargeTrade
         */
        LargeTrade.fromObject = function fromObject(object) {
            if (object instanceof $root.market.LargeTrade)
                return object;
            let message = new $root.market.LargeTrade();
            if (object.price != null)
                message.price = Number(object.price);
            if (object.size != null)
                if ($util.Long)
                    (message.size = $util.Long.fromValue(object.size)).unsigned = true;
                else if (typeof object.size === "string")
                    message.size = parseInt(object.size, 10);
                else if (typeof object.size === "number")
                    message.size = object.size;
                else if (typeof object.size === "object")
                    message.size = new $util.LongBits(object.size.low >>> 0, object.size.high >>> 0).toNumber(true);
            switch (object.side) {
            default:
                if (typeof object.side === "number") {
                    message.side = object.side;
                    break;
                }
                break;
            case "SIDE_UNKNOWN":
            case 0:
                message.side = 0;
                break;
            case "SIDE_BUY":
            case 1:
                message.side = 1;
                break;
            case "SIDE_SELL":
            case 2:
                message.side = 2;
                break;
            }
            if (object.timestampMs != null)
                if ($util.Long)
                    (message.timestampMs = $util.Long.fromValue(object.timestampMs)).unsigned = false;
                else if (typeof object.timestampMs === "string")
                    message.timestampMs = parseInt(object.timestampMs, 10);
                else if (typeof object.timestampMs === "number")
                    message.timestampMs = object.timestampMs;
                else if (typeof object.timestampMs === "object")
                    message.timestampMs = new $util.LongBits(object.timestampMs.low >>> 0, object.timestampMs.high >>> 0).toNumber();
            return message;
        };

        /**
         * Creates a plain object from a LargeTrade message. Also converts values to other types if specified.
         * @function toObject
         * @memberof market.LargeTrade
         * @static
         * @param {market.LargeTrade} message LargeTrade
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        LargeTrade.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.defaults) {
                object.price = 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, true);
                    object.size = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.size = options.longs === String ? "0" : 0;
                object.side = options.enums === String ? "SIDE_UNKNOWN" : 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.timestampMs = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.timestampMs = options.longs === String ? "0" : 0;
            }
            if (message.price != null && message.hasOwnProperty("price"))
                object.price = options.json && !isFinite(message.price) ? String(message.price) : message.price;
            if (message.size != null && message.hasOwnProperty("size"))
                if (typeof message.size === "number")
                    object.size = options.longs === String ? String(message.size) : message.size;
                else
                    object.size = options.longs === String ? $util.Long.prototype.toString.call(message.size) : options.longs === Number ? new $util.LongBits(message.size.low >>> 0, message.size.high >>> 0).toNumber(true) : message.size;
            if (message.side != null && message.hasOwnProperty("side"))
                object.side = options.enums === String ? $root.market.TradeSide[message.side] === undefined ? message.side : $root.market.TradeSide[message.side] : message.side;
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (typeof message.timestampMs === "number")
                    object.timestampMs = options.longs === String ? String(message.timestampMs) : message.timestampMs;
                else
                    object.timestampMs = options.longs === String ? $util.Long.prototype.toString.call(message.timestampMs) : options.longs === Number ? new $util.LongBits(message.timestampMs.low >>> 0, message.timestampMs.high >>> 0).toNumber() : message.timestampMs;
            return object;
        };

        /**
         * Converts this LargeTrade to JSON.
         * @function toJSON
         * @memberof market.LargeTrade
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        LargeTrade.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for LargeTrade
         * @function getTypeUrl
         * @memberof market.LargeTrade
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        LargeTrade.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/market.LargeTrade";
        };

        return LargeTrade;
    })();

    market.OptionTrade = (function() {

        /**
         * Properties of an OptionTrade.
         * @memberof market
         * @interface IOptionTrade
         * @property {string|null} [root] OptionTrade root
         * @property {number|null} [strike] OptionTrade strike
         * @property {string|null} [right] OptionTrade right
         * @property {number|null} [price] OptionTrade price
         * @property {number|Long|null} [size] OptionTrade size
         * @property {number|null} [premium] OptionTrade premium
         * @property {string|null} [side] OptionTrade side
         * @property {number|null} [iv] OptionTrade iv
         * @property {number|null} [delta] OptionTrade delta
         * @property {number|null} [gamma] OptionTrade gamma
         * @property {number|null} [vpin] OptionTrade vpin
         * @property {number|null} [sms] OptionTrade sms
         * @property {number|null} [expiration] OptionTrade expiration
         * @property {string|null} [exchange] OptionTrade exchange
         * @property {number|Long|null} [timestampMs] OptionTrade timestampMs
         * @property {number|Long|null} [msOfDay] OptionTrade msOfDay
         * @property {number|null} [condition] OptionTrade condition
         */

        /**
         * Constructs a new OptionTrade.
         * @memberof market
         * @classdesc Represents an OptionTrade.
         * @implements IOptionTrade
         * @constructor
         * @param {market.IOptionTrade=} [properties] Properties to set
         */
        function OptionTrade(properties) {
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * OptionTrade root.
         * @member {string} root
         * @memberof market.OptionTrade
         * @instance
         */
        OptionTrade.prototype.root = "";

        /**
         * OptionTrade strike.
         * @member {number} strike
         * @memberof market.OptionTrade
         * @instance
         */
        OptionTrade.prototype.strike = 0;

        /**
         * OptionTrade right.
         * @member {string} right
         * @memberof market.OptionTrade
         * @instance
         */
        OptionTrade.prototype.right = "";

        /**
         * OptionTrade price.
         * @member {number} price
         * @memberof market.OptionTrade
         * @instance
         */
        OptionTrade.prototype.price = 0;

        /**
         * OptionTrade size.
         * @member {number|Long} size
         * @memberof market.OptionTrade
         * @instance
         */
        OptionTrade.prototype.size = $util.Long ? $util.Long.fromBits(0,0,true) : 0;

        /**
         * OptionTrade premium.
         * @member {number} premium
         * @memberof market.OptionTrade
         * @instance
         */
        OptionTrade.prototype.premium = 0;

        /**
         * OptionTrade side.
         * @member {string} side
         * @memberof market.OptionTrade
         * @instance
         */
        OptionTrade.prototype.side = "";

        /**
         * OptionTrade iv.
         * @member {number} iv
         * @memberof market.OptionTrade
         * @instance
         */
        OptionTrade.prototype.iv = 0;

        /**
         * OptionTrade delta.
         * @member {number} delta
         * @memberof market.OptionTrade
         * @instance
         */
        OptionTrade.prototype.delta = 0;

        /**
         * OptionTrade gamma.
         * @member {number} gamma
         * @memberof market.OptionTrade
         * @instance
         */
        OptionTrade.prototype.gamma = 0;

        /**
         * OptionTrade vpin.
         * @member {number} vpin
         * @memberof market.OptionTrade
         * @instance
         */
        OptionTrade.prototype.vpin = 0;

        /**
         * OptionTrade sms.
         * @member {number} sms
         * @memberof market.OptionTrade
         * @instance
         */
        OptionTrade.prototype.sms = 0;

        /**
         * OptionTrade expiration.
         * @member {number} expiration
         * @memberof market.OptionTrade
         * @instance
         */
        OptionTrade.prototype.expiration = 0;

        /**
         * OptionTrade exchange.
         * @member {string} exchange
         * @memberof market.OptionTrade
         * @instance
         */
        OptionTrade.prototype.exchange = "";

        /**
         * OptionTrade timestampMs.
         * @member {number|Long} timestampMs
         * @memberof market.OptionTrade
         * @instance
         */
        OptionTrade.prototype.timestampMs = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * OptionTrade msOfDay.
         * @member {number|Long} msOfDay
         * @memberof market.OptionTrade
         * @instance
         */
        OptionTrade.prototype.msOfDay = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * OptionTrade condition.
         * @member {number} condition
         * @memberof market.OptionTrade
         * @instance
         */
        OptionTrade.prototype.condition = 0;

        /**
         * Creates a new OptionTrade instance using the specified properties.
         * @function create
         * @memberof market.OptionTrade
         * @static
         * @param {market.IOptionTrade=} [properties] Properties to set
         * @returns {market.OptionTrade} OptionTrade instance
         */
        OptionTrade.create = function create(properties) {
            return new OptionTrade(properties);
        };

        /**
         * Encodes the specified OptionTrade message. Does not implicitly {@link market.OptionTrade.verify|verify} messages.
         * @function encode
         * @memberof market.OptionTrade
         * @static
         * @param {market.IOptionTrade} message OptionTrade message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        OptionTrade.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.root != null && Object.hasOwnProperty.call(message, "root"))
                writer.uint32(/* id 1, wireType 2 =*/10).string(message.root);
            if (message.strike != null && Object.hasOwnProperty.call(message, "strike"))
                writer.uint32(/* id 2, wireType 1 =*/17).double(message.strike);
            if (message.right != null && Object.hasOwnProperty.call(message, "right"))
                writer.uint32(/* id 3, wireType 2 =*/26).string(message.right);
            if (message.price != null && Object.hasOwnProperty.call(message, "price"))
                writer.uint32(/* id 4, wireType 1 =*/33).double(message.price);
            if (message.size != null && Object.hasOwnProperty.call(message, "size"))
                writer.uint32(/* id 5, wireType 0 =*/40).uint64(message.size);
            if (message.premium != null && Object.hasOwnProperty.call(message, "premium"))
                writer.uint32(/* id 6, wireType 1 =*/49).double(message.premium);
            if (message.side != null && Object.hasOwnProperty.call(message, "side"))
                writer.uint32(/* id 7, wireType 2 =*/58).string(message.side);
            if (message.iv != null && Object.hasOwnProperty.call(message, "iv"))
                writer.uint32(/* id 8, wireType 1 =*/65).double(message.iv);
            if (message.delta != null && Object.hasOwnProperty.call(message, "delta"))
                writer.uint32(/* id 9, wireType 1 =*/73).double(message.delta);
            if (message.gamma != null && Object.hasOwnProperty.call(message, "gamma"))
                writer.uint32(/* id 10, wireType 1 =*/81).double(message.gamma);
            if (message.vpin != null && Object.hasOwnProperty.call(message, "vpin"))
                writer.uint32(/* id 11, wireType 1 =*/89).double(message.vpin);
            if (message.sms != null && Object.hasOwnProperty.call(message, "sms"))
                writer.uint32(/* id 12, wireType 0 =*/96).uint32(message.sms);
            if (message.expiration != null && Object.hasOwnProperty.call(message, "expiration"))
                writer.uint32(/* id 13, wireType 0 =*/104).int32(message.expiration);
            if (message.exchange != null && Object.hasOwnProperty.call(message, "exchange"))
                writer.uint32(/* id 14, wireType 2 =*/114).string(message.exchange);
            if (message.timestampMs != null && Object.hasOwnProperty.call(message, "timestampMs"))
                writer.uint32(/* id 15, wireType 0 =*/120).int64(message.timestampMs);
            if (message.msOfDay != null && Object.hasOwnProperty.call(message, "msOfDay"))
                writer.uint32(/* id 16, wireType 0 =*/128).int64(message.msOfDay);
            if (message.condition != null && Object.hasOwnProperty.call(message, "condition"))
                writer.uint32(/* id 17, wireType 0 =*/136).int32(message.condition);
            return writer;
        };

        /**
         * Encodes the specified OptionTrade message, length delimited. Does not implicitly {@link market.OptionTrade.verify|verify} messages.
         * @function encodeDelimited
         * @memberof market.OptionTrade
         * @static
         * @param {market.IOptionTrade} message OptionTrade message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        OptionTrade.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes an OptionTrade message from the specified reader or buffer.
         * @function decode
         * @memberof market.OptionTrade
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {market.OptionTrade} OptionTrade
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        OptionTrade.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.market.OptionTrade();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.root = reader.string();
                        break;
                    }
                case 2: {
                        message.strike = reader.double();
                        break;
                    }
                case 3: {
                        message.right = reader.string();
                        break;
                    }
                case 4: {
                        message.price = reader.double();
                        break;
                    }
                case 5: {
                        message.size = reader.uint64();
                        break;
                    }
                case 6: {
                        message.premium = reader.double();
                        break;
                    }
                case 7: {
                        message.side = reader.string();
                        break;
                    }
                case 8: {
                        message.iv = reader.double();
                        break;
                    }
                case 9: {
                        message.delta = reader.double();
                        break;
                    }
                case 10: {
                        message.gamma = reader.double();
                        break;
                    }
                case 11: {
                        message.vpin = reader.double();
                        break;
                    }
                case 12: {
                        message.sms = reader.uint32();
                        break;
                    }
                case 13: {
                        message.expiration = reader.int32();
                        break;
                    }
                case 14: {
                        message.exchange = reader.string();
                        break;
                    }
                case 15: {
                        message.timestampMs = reader.int64();
                        break;
                    }
                case 16: {
                        message.msOfDay = reader.int64();
                        break;
                    }
                case 17: {
                        message.condition = reader.int32();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes an OptionTrade message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof market.OptionTrade
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {market.OptionTrade} OptionTrade
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        OptionTrade.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies an OptionTrade message.
         * @function verify
         * @memberof market.OptionTrade
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        OptionTrade.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.root != null && message.hasOwnProperty("root"))
                if (!$util.isString(message.root))
                    return "root: string expected";
            if (message.strike != null && message.hasOwnProperty("strike"))
                if (typeof message.strike !== "number")
                    return "strike: number expected";
            if (message.right != null && message.hasOwnProperty("right"))
                if (!$util.isString(message.right))
                    return "right: string expected";
            if (message.price != null && message.hasOwnProperty("price"))
                if (typeof message.price !== "number")
                    return "price: number expected";
            if (message.size != null && message.hasOwnProperty("size"))
                if (!$util.isInteger(message.size) && !(message.size && $util.isInteger(message.size.low) && $util.isInteger(message.size.high)))
                    return "size: integer|Long expected";
            if (message.premium != null && message.hasOwnProperty("premium"))
                if (typeof message.premium !== "number")
                    return "premium: number expected";
            if (message.side != null && message.hasOwnProperty("side"))
                if (!$util.isString(message.side))
                    return "side: string expected";
            if (message.iv != null && message.hasOwnProperty("iv"))
                if (typeof message.iv !== "number")
                    return "iv: number expected";
            if (message.delta != null && message.hasOwnProperty("delta"))
                if (typeof message.delta !== "number")
                    return "delta: number expected";
            if (message.gamma != null && message.hasOwnProperty("gamma"))
                if (typeof message.gamma !== "number")
                    return "gamma: number expected";
            if (message.vpin != null && message.hasOwnProperty("vpin"))
                if (typeof message.vpin !== "number")
                    return "vpin: number expected";
            if (message.sms != null && message.hasOwnProperty("sms"))
                if (!$util.isInteger(message.sms))
                    return "sms: integer expected";
            if (message.expiration != null && message.hasOwnProperty("expiration"))
                if (!$util.isInteger(message.expiration))
                    return "expiration: integer expected";
            if (message.exchange != null && message.hasOwnProperty("exchange"))
                if (!$util.isString(message.exchange))
                    return "exchange: string expected";
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (!$util.isInteger(message.timestampMs) && !(message.timestampMs && $util.isInteger(message.timestampMs.low) && $util.isInteger(message.timestampMs.high)))
                    return "timestampMs: integer|Long expected";
            if (message.msOfDay != null && message.hasOwnProperty("msOfDay"))
                if (!$util.isInteger(message.msOfDay) && !(message.msOfDay && $util.isInteger(message.msOfDay.low) && $util.isInteger(message.msOfDay.high)))
                    return "msOfDay: integer|Long expected";
            if (message.condition != null && message.hasOwnProperty("condition"))
                if (!$util.isInteger(message.condition))
                    return "condition: integer expected";
            return null;
        };

        /**
         * Creates an OptionTrade message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof market.OptionTrade
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {market.OptionTrade} OptionTrade
         */
        OptionTrade.fromObject = function fromObject(object) {
            if (object instanceof $root.market.OptionTrade)
                return object;
            let message = new $root.market.OptionTrade();
            if (object.root != null)
                message.root = String(object.root);
            if (object.strike != null)
                message.strike = Number(object.strike);
            if (object.right != null)
                message.right = String(object.right);
            if (object.price != null)
                message.price = Number(object.price);
            if (object.size != null)
                if ($util.Long)
                    (message.size = $util.Long.fromValue(object.size)).unsigned = true;
                else if (typeof object.size === "string")
                    message.size = parseInt(object.size, 10);
                else if (typeof object.size === "number")
                    message.size = object.size;
                else if (typeof object.size === "object")
                    message.size = new $util.LongBits(object.size.low >>> 0, object.size.high >>> 0).toNumber(true);
            if (object.premium != null)
                message.premium = Number(object.premium);
            if (object.side != null)
                message.side = String(object.side);
            if (object.iv != null)
                message.iv = Number(object.iv);
            if (object.delta != null)
                message.delta = Number(object.delta);
            if (object.gamma != null)
                message.gamma = Number(object.gamma);
            if (object.vpin != null)
                message.vpin = Number(object.vpin);
            if (object.sms != null)
                message.sms = object.sms >>> 0;
            if (object.expiration != null)
                message.expiration = object.expiration | 0;
            if (object.exchange != null)
                message.exchange = String(object.exchange);
            if (object.timestampMs != null)
                if ($util.Long)
                    (message.timestampMs = $util.Long.fromValue(object.timestampMs)).unsigned = false;
                else if (typeof object.timestampMs === "string")
                    message.timestampMs = parseInt(object.timestampMs, 10);
                else if (typeof object.timestampMs === "number")
                    message.timestampMs = object.timestampMs;
                else if (typeof object.timestampMs === "object")
                    message.timestampMs = new $util.LongBits(object.timestampMs.low >>> 0, object.timestampMs.high >>> 0).toNumber();
            if (object.msOfDay != null)
                if ($util.Long)
                    (message.msOfDay = $util.Long.fromValue(object.msOfDay)).unsigned = false;
                else if (typeof object.msOfDay === "string")
                    message.msOfDay = parseInt(object.msOfDay, 10);
                else if (typeof object.msOfDay === "number")
                    message.msOfDay = object.msOfDay;
                else if (typeof object.msOfDay === "object")
                    message.msOfDay = new $util.LongBits(object.msOfDay.low >>> 0, object.msOfDay.high >>> 0).toNumber();
            if (object.condition != null)
                message.condition = object.condition | 0;
            return message;
        };

        /**
         * Creates a plain object from an OptionTrade message. Also converts values to other types if specified.
         * @function toObject
         * @memberof market.OptionTrade
         * @static
         * @param {market.OptionTrade} message OptionTrade
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        OptionTrade.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.defaults) {
                object.root = "";
                object.strike = 0;
                object.right = "";
                object.price = 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, true);
                    object.size = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.size = options.longs === String ? "0" : 0;
                object.premium = 0;
                object.side = "";
                object.iv = 0;
                object.delta = 0;
                object.gamma = 0;
                object.vpin = 0;
                object.sms = 0;
                object.expiration = 0;
                object.exchange = "";
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.timestampMs = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.timestampMs = options.longs === String ? "0" : 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.msOfDay = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.msOfDay = options.longs === String ? "0" : 0;
                object.condition = 0;
            }
            if (message.root != null && message.hasOwnProperty("root"))
                object.root = message.root;
            if (message.strike != null && message.hasOwnProperty("strike"))
                object.strike = options.json && !isFinite(message.strike) ? String(message.strike) : message.strike;
            if (message.right != null && message.hasOwnProperty("right"))
                object.right = message.right;
            if (message.price != null && message.hasOwnProperty("price"))
                object.price = options.json && !isFinite(message.price) ? String(message.price) : message.price;
            if (message.size != null && message.hasOwnProperty("size"))
                if (typeof message.size === "number")
                    object.size = options.longs === String ? String(message.size) : message.size;
                else
                    object.size = options.longs === String ? $util.Long.prototype.toString.call(message.size) : options.longs === Number ? new $util.LongBits(message.size.low >>> 0, message.size.high >>> 0).toNumber(true) : message.size;
            if (message.premium != null && message.hasOwnProperty("premium"))
                object.premium = options.json && !isFinite(message.premium) ? String(message.premium) : message.premium;
            if (message.side != null && message.hasOwnProperty("side"))
                object.side = message.side;
            if (message.iv != null && message.hasOwnProperty("iv"))
                object.iv = options.json && !isFinite(message.iv) ? String(message.iv) : message.iv;
            if (message.delta != null && message.hasOwnProperty("delta"))
                object.delta = options.json && !isFinite(message.delta) ? String(message.delta) : message.delta;
            if (message.gamma != null && message.hasOwnProperty("gamma"))
                object.gamma = options.json && !isFinite(message.gamma) ? String(message.gamma) : message.gamma;
            if (message.vpin != null && message.hasOwnProperty("vpin"))
                object.vpin = options.json && !isFinite(message.vpin) ? String(message.vpin) : message.vpin;
            if (message.sms != null && message.hasOwnProperty("sms"))
                object.sms = message.sms;
            if (message.expiration != null && message.hasOwnProperty("expiration"))
                object.expiration = message.expiration;
            if (message.exchange != null && message.hasOwnProperty("exchange"))
                object.exchange = message.exchange;
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (typeof message.timestampMs === "number")
                    object.timestampMs = options.longs === String ? String(message.timestampMs) : message.timestampMs;
                else
                    object.timestampMs = options.longs === String ? $util.Long.prototype.toString.call(message.timestampMs) : options.longs === Number ? new $util.LongBits(message.timestampMs.low >>> 0, message.timestampMs.high >>> 0).toNumber() : message.timestampMs;
            if (message.msOfDay != null && message.hasOwnProperty("msOfDay"))
                if (typeof message.msOfDay === "number")
                    object.msOfDay = options.longs === String ? String(message.msOfDay) : message.msOfDay;
                else
                    object.msOfDay = options.longs === String ? $util.Long.prototype.toString.call(message.msOfDay) : options.longs === Number ? new $util.LongBits(message.msOfDay.low >>> 0, message.msOfDay.high >>> 0).toNumber() : message.msOfDay;
            if (message.condition != null && message.hasOwnProperty("condition"))
                object.condition = message.condition;
            return object;
        };

        /**
         * Converts this OptionTrade to JSON.
         * @function toJSON
         * @memberof market.OptionTrade
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        OptionTrade.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for OptionTrade
         * @function getTypeUrl
         * @memberof market.OptionTrade
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        OptionTrade.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/market.OptionTrade";
        };

        return OptionTrade;
    })();

    market.Heartbeat = (function() {

        /**
         * Properties of a Heartbeat.
         * @memberof market
         * @interface IHeartbeat
         * @property {number|Long|null} [timestampMs] Heartbeat timestampMs
         * @property {number|Long|null} [ticksProcessed] Heartbeat ticksProcessed
         * @property {number|null} [lastPrice] Heartbeat lastPrice
         * @property {string|null} [dataSource] Heartbeat dataSource
         */

        /**
         * Constructs a new Heartbeat.
         * @memberof market
         * @classdesc Represents a Heartbeat.
         * @implements IHeartbeat
         * @constructor
         * @param {market.IHeartbeat=} [properties] Properties to set
         */
        function Heartbeat(properties) {
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * Heartbeat timestampMs.
         * @member {number|Long} timestampMs
         * @memberof market.Heartbeat
         * @instance
         */
        Heartbeat.prototype.timestampMs = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * Heartbeat ticksProcessed.
         * @member {number|Long} ticksProcessed
         * @memberof market.Heartbeat
         * @instance
         */
        Heartbeat.prototype.ticksProcessed = $util.Long ? $util.Long.fromBits(0,0,true) : 0;

        /**
         * Heartbeat lastPrice.
         * @member {number} lastPrice
         * @memberof market.Heartbeat
         * @instance
         */
        Heartbeat.prototype.lastPrice = 0;

        /**
         * Heartbeat dataSource.
         * @member {string} dataSource
         * @memberof market.Heartbeat
         * @instance
         */
        Heartbeat.prototype.dataSource = "";

        /**
         * Creates a new Heartbeat instance using the specified properties.
         * @function create
         * @memberof market.Heartbeat
         * @static
         * @param {market.IHeartbeat=} [properties] Properties to set
         * @returns {market.Heartbeat} Heartbeat instance
         */
        Heartbeat.create = function create(properties) {
            return new Heartbeat(properties);
        };

        /**
         * Encodes the specified Heartbeat message. Does not implicitly {@link market.Heartbeat.verify|verify} messages.
         * @function encode
         * @memberof market.Heartbeat
         * @static
         * @param {market.IHeartbeat} message Heartbeat message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Heartbeat.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.timestampMs != null && Object.hasOwnProperty.call(message, "timestampMs"))
                writer.uint32(/* id 1, wireType 0 =*/8).int64(message.timestampMs);
            if (message.ticksProcessed != null && Object.hasOwnProperty.call(message, "ticksProcessed"))
                writer.uint32(/* id 2, wireType 0 =*/16).uint64(message.ticksProcessed);
            if (message.lastPrice != null && Object.hasOwnProperty.call(message, "lastPrice"))
                writer.uint32(/* id 3, wireType 1 =*/25).double(message.lastPrice);
            if (message.dataSource != null && Object.hasOwnProperty.call(message, "dataSource"))
                writer.uint32(/* id 4, wireType 2 =*/34).string(message.dataSource);
            return writer;
        };

        /**
         * Encodes the specified Heartbeat message, length delimited. Does not implicitly {@link market.Heartbeat.verify|verify} messages.
         * @function encodeDelimited
         * @memberof market.Heartbeat
         * @static
         * @param {market.IHeartbeat} message Heartbeat message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Heartbeat.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a Heartbeat message from the specified reader or buffer.
         * @function decode
         * @memberof market.Heartbeat
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {market.Heartbeat} Heartbeat
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Heartbeat.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.market.Heartbeat();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.timestampMs = reader.int64();
                        break;
                    }
                case 2: {
                        message.ticksProcessed = reader.uint64();
                        break;
                    }
                case 3: {
                        message.lastPrice = reader.double();
                        break;
                    }
                case 4: {
                        message.dataSource = reader.string();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a Heartbeat message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof market.Heartbeat
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {market.Heartbeat} Heartbeat
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Heartbeat.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a Heartbeat message.
         * @function verify
         * @memberof market.Heartbeat
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        Heartbeat.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (!$util.isInteger(message.timestampMs) && !(message.timestampMs && $util.isInteger(message.timestampMs.low) && $util.isInteger(message.timestampMs.high)))
                    return "timestampMs: integer|Long expected";
            if (message.ticksProcessed != null && message.hasOwnProperty("ticksProcessed"))
                if (!$util.isInteger(message.ticksProcessed) && !(message.ticksProcessed && $util.isInteger(message.ticksProcessed.low) && $util.isInteger(message.ticksProcessed.high)))
                    return "ticksProcessed: integer|Long expected";
            if (message.lastPrice != null && message.hasOwnProperty("lastPrice"))
                if (typeof message.lastPrice !== "number")
                    return "lastPrice: number expected";
            if (message.dataSource != null && message.hasOwnProperty("dataSource"))
                if (!$util.isString(message.dataSource))
                    return "dataSource: string expected";
            return null;
        };

        /**
         * Creates a Heartbeat message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof market.Heartbeat
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {market.Heartbeat} Heartbeat
         */
        Heartbeat.fromObject = function fromObject(object) {
            if (object instanceof $root.market.Heartbeat)
                return object;
            let message = new $root.market.Heartbeat();
            if (object.timestampMs != null)
                if ($util.Long)
                    (message.timestampMs = $util.Long.fromValue(object.timestampMs)).unsigned = false;
                else if (typeof object.timestampMs === "string")
                    message.timestampMs = parseInt(object.timestampMs, 10);
                else if (typeof object.timestampMs === "number")
                    message.timestampMs = object.timestampMs;
                else if (typeof object.timestampMs === "object")
                    message.timestampMs = new $util.LongBits(object.timestampMs.low >>> 0, object.timestampMs.high >>> 0).toNumber();
            if (object.ticksProcessed != null)
                if ($util.Long)
                    (message.ticksProcessed = $util.Long.fromValue(object.ticksProcessed)).unsigned = true;
                else if (typeof object.ticksProcessed === "string")
                    message.ticksProcessed = parseInt(object.ticksProcessed, 10);
                else if (typeof object.ticksProcessed === "number")
                    message.ticksProcessed = object.ticksProcessed;
                else if (typeof object.ticksProcessed === "object")
                    message.ticksProcessed = new $util.LongBits(object.ticksProcessed.low >>> 0, object.ticksProcessed.high >>> 0).toNumber(true);
            if (object.lastPrice != null)
                message.lastPrice = Number(object.lastPrice);
            if (object.dataSource != null)
                message.dataSource = String(object.dataSource);
            return message;
        };

        /**
         * Creates a plain object from a Heartbeat message. Also converts values to other types if specified.
         * @function toObject
         * @memberof market.Heartbeat
         * @static
         * @param {market.Heartbeat} message Heartbeat
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        Heartbeat.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.defaults) {
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.timestampMs = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.timestampMs = options.longs === String ? "0" : 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, true);
                    object.ticksProcessed = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.ticksProcessed = options.longs === String ? "0" : 0;
                object.lastPrice = 0;
                object.dataSource = "";
            }
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (typeof message.timestampMs === "number")
                    object.timestampMs = options.longs === String ? String(message.timestampMs) : message.timestampMs;
                else
                    object.timestampMs = options.longs === String ? $util.Long.prototype.toString.call(message.timestampMs) : options.longs === Number ? new $util.LongBits(message.timestampMs.low >>> 0, message.timestampMs.high >>> 0).toNumber() : message.timestampMs;
            if (message.ticksProcessed != null && message.hasOwnProperty("ticksProcessed"))
                if (typeof message.ticksProcessed === "number")
                    object.ticksProcessed = options.longs === String ? String(message.ticksProcessed) : message.ticksProcessed;
                else
                    object.ticksProcessed = options.longs === String ? $util.Long.prototype.toString.call(message.ticksProcessed) : options.longs === Number ? new $util.LongBits(message.ticksProcessed.low >>> 0, message.ticksProcessed.high >>> 0).toNumber(true) : message.ticksProcessed;
            if (message.lastPrice != null && message.hasOwnProperty("lastPrice"))
                object.lastPrice = options.json && !isFinite(message.lastPrice) ? String(message.lastPrice) : message.lastPrice;
            if (message.dataSource != null && message.hasOwnProperty("dataSource"))
                object.dataSource = message.dataSource;
            return object;
        };

        /**
         * Converts this Heartbeat to JSON.
         * @function toJSON
         * @memberof market.Heartbeat
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        Heartbeat.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for Heartbeat
         * @function getTypeUrl
         * @memberof market.Heartbeat
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        Heartbeat.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/market.Heartbeat";
        };

        return Heartbeat;
    })();

    market.ExternalJson = (function() {

        /**
         * Properties of an ExternalJson.
         * @memberof market
         * @interface IExternalJson
         * @property {string|null} [json] ExternalJson json
         */

        /**
         * Constructs a new ExternalJson.
         * @memberof market
         * @classdesc Represents an ExternalJson.
         * @implements IExternalJson
         * @constructor
         * @param {market.IExternalJson=} [properties] Properties to set
         */
        function ExternalJson(properties) {
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * ExternalJson json.
         * @member {string} json
         * @memberof market.ExternalJson
         * @instance
         */
        ExternalJson.prototype.json = "";

        /**
         * Creates a new ExternalJson instance using the specified properties.
         * @function create
         * @memberof market.ExternalJson
         * @static
         * @param {market.IExternalJson=} [properties] Properties to set
         * @returns {market.ExternalJson} ExternalJson instance
         */
        ExternalJson.create = function create(properties) {
            return new ExternalJson(properties);
        };

        /**
         * Encodes the specified ExternalJson message. Does not implicitly {@link market.ExternalJson.verify|verify} messages.
         * @function encode
         * @memberof market.ExternalJson
         * @static
         * @param {market.IExternalJson} message ExternalJson message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        ExternalJson.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.json != null && Object.hasOwnProperty.call(message, "json"))
                writer.uint32(/* id 1, wireType 2 =*/10).string(message.json);
            return writer;
        };

        /**
         * Encodes the specified ExternalJson message, length delimited. Does not implicitly {@link market.ExternalJson.verify|verify} messages.
         * @function encodeDelimited
         * @memberof market.ExternalJson
         * @static
         * @param {market.IExternalJson} message ExternalJson message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        ExternalJson.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes an ExternalJson message from the specified reader or buffer.
         * @function decode
         * @memberof market.ExternalJson
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {market.ExternalJson} ExternalJson
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        ExternalJson.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.market.ExternalJson();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.json = reader.string();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes an ExternalJson message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof market.ExternalJson
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {market.ExternalJson} ExternalJson
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        ExternalJson.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies an ExternalJson message.
         * @function verify
         * @memberof market.ExternalJson
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        ExternalJson.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.json != null && message.hasOwnProperty("json"))
                if (!$util.isString(message.json))
                    return "json: string expected";
            return null;
        };

        /**
         * Creates an ExternalJson message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof market.ExternalJson
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {market.ExternalJson} ExternalJson
         */
        ExternalJson.fromObject = function fromObject(object) {
            if (object instanceof $root.market.ExternalJson)
                return object;
            let message = new $root.market.ExternalJson();
            if (object.json != null)
                message.json = String(object.json);
            return message;
        };

        /**
         * Creates a plain object from an ExternalJson message. Also converts values to other types if specified.
         * @function toObject
         * @memberof market.ExternalJson
         * @static
         * @param {market.ExternalJson} message ExternalJson
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        ExternalJson.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.defaults)
                object.json = "";
            if (message.json != null && message.hasOwnProperty("json"))
                object.json = message.json;
            return object;
        };

        /**
         * Converts this ExternalJson to JSON.
         * @function toJSON
         * @memberof market.ExternalJson
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        ExternalJson.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for ExternalJson
         * @function getTypeUrl
         * @memberof market.ExternalJson
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        ExternalJson.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/market.ExternalJson";
        };

        return ExternalJson;
    })();

    market.MarketMessage = (function() {

        /**
         * Properties of a MarketMessage.
         * @memberof market
         * @interface IMarketMessage
         * @property {market.ITick|null} [tick] MarketMessage tick
         * @property {market.IQuote|null} [quote] MarketMessage quote
         * @property {market.ICandle|null} [candle] MarketMessage candle
         * @property {market.ICvd|null} [cvd] MarketMessage cvd
         * @property {market.IFootprint|null} [footprint] MarketMessage footprint
         * @property {market.ISweep|null} [sweep] MarketMessage sweep
         * @property {market.IImbalance|null} [imbalance] MarketMessage imbalance
         * @property {market.IAbsorption|null} [absorption] MarketMessage absorption
         * @property {market.IDeltaFlip|null} [deltaFlip] MarketMessage deltaFlip
         * @property {market.ILargeTrade|null} [largeTrade] MarketMessage largeTrade
         * @property {market.IOptionTrade|null} [optionTrade] MarketMessage optionTrade
         * @property {market.IHeartbeat|null} [heartbeat] MarketMessage heartbeat
         * @property {market.IExternalJson|null} [external] MarketMessage external
         */

        /**
         * Constructs a new MarketMessage.
         * @memberof market
         * @classdesc Represents a MarketMessage.
         * @implements IMarketMessage
         * @constructor
         * @param {market.IMarketMessage=} [properties] Properties to set
         */
        function MarketMessage(properties) {
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * MarketMessage tick.
         * @member {market.ITick|null|undefined} tick
         * @memberof market.MarketMessage
         * @instance
         */
        MarketMessage.prototype.tick = null;

        /**
         * MarketMessage quote.
         * @member {market.IQuote|null|undefined} quote
         * @memberof market.MarketMessage
         * @instance
         */
        MarketMessage.prototype.quote = null;

        /**
         * MarketMessage candle.
         * @member {market.ICandle|null|undefined} candle
         * @memberof market.MarketMessage
         * @instance
         */
        MarketMessage.prototype.candle = null;

        /**
         * MarketMessage cvd.
         * @member {market.ICvd|null|undefined} cvd
         * @memberof market.MarketMessage
         * @instance
         */
        MarketMessage.prototype.cvd = null;

        /**
         * MarketMessage footprint.
         * @member {market.IFootprint|null|undefined} footprint
         * @memberof market.MarketMessage
         * @instance
         */
        MarketMessage.prototype.footprint = null;

        /**
         * MarketMessage sweep.
         * @member {market.ISweep|null|undefined} sweep
         * @memberof market.MarketMessage
         * @instance
         */
        MarketMessage.prototype.sweep = null;

        /**
         * MarketMessage imbalance.
         * @member {market.IImbalance|null|undefined} imbalance
         * @memberof market.MarketMessage
         * @instance
         */
        MarketMessage.prototype.imbalance = null;

        /**
         * MarketMessage absorption.
         * @member {market.IAbsorption|null|undefined} absorption
         * @memberof market.MarketMessage
         * @instance
         */
        MarketMessage.prototype.absorption = null;

        /**
         * MarketMessage deltaFlip.
         * @member {market.IDeltaFlip|null|undefined} deltaFlip
         * @memberof market.MarketMessage
         * @instance
         */
        MarketMessage.prototype.deltaFlip = null;

        /**
         * MarketMessage largeTrade.
         * @member {market.ILargeTrade|null|undefined} largeTrade
         * @memberof market.MarketMessage
         * @instance
         */
        MarketMessage.prototype.largeTrade = null;

        /**
         * MarketMessage optionTrade.
         * @member {market.IOptionTrade|null|undefined} optionTrade
         * @memberof market.MarketMessage
         * @instance
         */
        MarketMessage.prototype.optionTrade = null;

        /**
         * MarketMessage heartbeat.
         * @member {market.IHeartbeat|null|undefined} heartbeat
         * @memberof market.MarketMessage
         * @instance
         */
        MarketMessage.prototype.heartbeat = null;

        /**
         * MarketMessage external.
         * @member {market.IExternalJson|null|undefined} external
         * @memberof market.MarketMessage
         * @instance
         */
        MarketMessage.prototype.external = null;

        // OneOf field names bound to virtual getters and setters
        let $oneOfFields;

        /**
         * MarketMessage payload.
         * @member {"tick"|"quote"|"candle"|"cvd"|"footprint"|"sweep"|"imbalance"|"absorption"|"deltaFlip"|"largeTrade"|"optionTrade"|"heartbeat"|"external"|undefined} payload
         * @memberof market.MarketMessage
         * @instance
         */
        Object.defineProperty(MarketMessage.prototype, "payload", {
            get: $util.oneOfGetter($oneOfFields = ["tick", "quote", "candle", "cvd", "footprint", "sweep", "imbalance", "absorption", "deltaFlip", "largeTrade", "optionTrade", "heartbeat", "external"]),
            set: $util.oneOfSetter($oneOfFields)
        });

        /**
         * Creates a new MarketMessage instance using the specified properties.
         * @function create
         * @memberof market.MarketMessage
         * @static
         * @param {market.IMarketMessage=} [properties] Properties to set
         * @returns {market.MarketMessage} MarketMessage instance
         */
        MarketMessage.create = function create(properties) {
            return new MarketMessage(properties);
        };

        /**
         * Encodes the specified MarketMessage message. Does not implicitly {@link market.MarketMessage.verify|verify} messages.
         * @function encode
         * @memberof market.MarketMessage
         * @static
         * @param {market.IMarketMessage} message MarketMessage message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        MarketMessage.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.tick != null && Object.hasOwnProperty.call(message, "tick"))
                $root.market.Tick.encode(message.tick, writer.uint32(/* id 1, wireType 2 =*/10).fork()).ldelim();
            if (message.quote != null && Object.hasOwnProperty.call(message, "quote"))
                $root.market.Quote.encode(message.quote, writer.uint32(/* id 2, wireType 2 =*/18).fork()).ldelim();
            if (message.candle != null && Object.hasOwnProperty.call(message, "candle"))
                $root.market.Candle.encode(message.candle, writer.uint32(/* id 3, wireType 2 =*/26).fork()).ldelim();
            if (message.cvd != null && Object.hasOwnProperty.call(message, "cvd"))
                $root.market.Cvd.encode(message.cvd, writer.uint32(/* id 4, wireType 2 =*/34).fork()).ldelim();
            if (message.footprint != null && Object.hasOwnProperty.call(message, "footprint"))
                $root.market.Footprint.encode(message.footprint, writer.uint32(/* id 5, wireType 2 =*/42).fork()).ldelim();
            if (message.sweep != null && Object.hasOwnProperty.call(message, "sweep"))
                $root.market.Sweep.encode(message.sweep, writer.uint32(/* id 6, wireType 2 =*/50).fork()).ldelim();
            if (message.imbalance != null && Object.hasOwnProperty.call(message, "imbalance"))
                $root.market.Imbalance.encode(message.imbalance, writer.uint32(/* id 7, wireType 2 =*/58).fork()).ldelim();
            if (message.absorption != null && Object.hasOwnProperty.call(message, "absorption"))
                $root.market.Absorption.encode(message.absorption, writer.uint32(/* id 8, wireType 2 =*/66).fork()).ldelim();
            if (message.deltaFlip != null && Object.hasOwnProperty.call(message, "deltaFlip"))
                $root.market.DeltaFlip.encode(message.deltaFlip, writer.uint32(/* id 9, wireType 2 =*/74).fork()).ldelim();
            if (message.largeTrade != null && Object.hasOwnProperty.call(message, "largeTrade"))
                $root.market.LargeTrade.encode(message.largeTrade, writer.uint32(/* id 10, wireType 2 =*/82).fork()).ldelim();
            if (message.optionTrade != null && Object.hasOwnProperty.call(message, "optionTrade"))
                $root.market.OptionTrade.encode(message.optionTrade, writer.uint32(/* id 11, wireType 2 =*/90).fork()).ldelim();
            if (message.heartbeat != null && Object.hasOwnProperty.call(message, "heartbeat"))
                $root.market.Heartbeat.encode(message.heartbeat, writer.uint32(/* id 12, wireType 2 =*/98).fork()).ldelim();
            if (message.external != null && Object.hasOwnProperty.call(message, "external"))
                $root.market.ExternalJson.encode(message.external, writer.uint32(/* id 13, wireType 2 =*/106).fork()).ldelim();
            return writer;
        };

        /**
         * Encodes the specified MarketMessage message, length delimited. Does not implicitly {@link market.MarketMessage.verify|verify} messages.
         * @function encodeDelimited
         * @memberof market.MarketMessage
         * @static
         * @param {market.IMarketMessage} message MarketMessage message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        MarketMessage.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a MarketMessage message from the specified reader or buffer.
         * @function decode
         * @memberof market.MarketMessage
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {market.MarketMessage} MarketMessage
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        MarketMessage.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.market.MarketMessage();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.tick = $root.market.Tick.decode(reader, reader.uint32());
                        break;
                    }
                case 2: {
                        message.quote = $root.market.Quote.decode(reader, reader.uint32());
                        break;
                    }
                case 3: {
                        message.candle = $root.market.Candle.decode(reader, reader.uint32());
                        break;
                    }
                case 4: {
                        message.cvd = $root.market.Cvd.decode(reader, reader.uint32());
                        break;
                    }
                case 5: {
                        message.footprint = $root.market.Footprint.decode(reader, reader.uint32());
                        break;
                    }
                case 6: {
                        message.sweep = $root.market.Sweep.decode(reader, reader.uint32());
                        break;
                    }
                case 7: {
                        message.imbalance = $root.market.Imbalance.decode(reader, reader.uint32());
                        break;
                    }
                case 8: {
                        message.absorption = $root.market.Absorption.decode(reader, reader.uint32());
                        break;
                    }
                case 9: {
                        message.deltaFlip = $root.market.DeltaFlip.decode(reader, reader.uint32());
                        break;
                    }
                case 10: {
                        message.largeTrade = $root.market.LargeTrade.decode(reader, reader.uint32());
                        break;
                    }
                case 11: {
                        message.optionTrade = $root.market.OptionTrade.decode(reader, reader.uint32());
                        break;
                    }
                case 12: {
                        message.heartbeat = $root.market.Heartbeat.decode(reader, reader.uint32());
                        break;
                    }
                case 13: {
                        message.external = $root.market.ExternalJson.decode(reader, reader.uint32());
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a MarketMessage message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof market.MarketMessage
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {market.MarketMessage} MarketMessage
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        MarketMessage.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a MarketMessage message.
         * @function verify
         * @memberof market.MarketMessage
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        MarketMessage.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            let properties = {};
            if (message.tick != null && message.hasOwnProperty("tick")) {
                properties.payload = 1;
                {
                    let error = $root.market.Tick.verify(message.tick);
                    if (error)
                        return "tick." + error;
                }
            }
            if (message.quote != null && message.hasOwnProperty("quote")) {
                if (properties.payload === 1)
                    return "payload: multiple values";
                properties.payload = 1;
                {
                    let error = $root.market.Quote.verify(message.quote);
                    if (error)
                        return "quote." + error;
                }
            }
            if (message.candle != null && message.hasOwnProperty("candle")) {
                if (properties.payload === 1)
                    return "payload: multiple values";
                properties.payload = 1;
                {
                    let error = $root.market.Candle.verify(message.candle);
                    if (error)
                        return "candle." + error;
                }
            }
            if (message.cvd != null && message.hasOwnProperty("cvd")) {
                if (properties.payload === 1)
                    return "payload: multiple values";
                properties.payload = 1;
                {
                    let error = $root.market.Cvd.verify(message.cvd);
                    if (error)
                        return "cvd." + error;
                }
            }
            if (message.footprint != null && message.hasOwnProperty("footprint")) {
                if (properties.payload === 1)
                    return "payload: multiple values";
                properties.payload = 1;
                {
                    let error = $root.market.Footprint.verify(message.footprint);
                    if (error)
                        return "footprint." + error;
                }
            }
            if (message.sweep != null && message.hasOwnProperty("sweep")) {
                if (properties.payload === 1)
                    return "payload: multiple values";
                properties.payload = 1;
                {
                    let error = $root.market.Sweep.verify(message.sweep);
                    if (error)
                        return "sweep." + error;
                }
            }
            if (message.imbalance != null && message.hasOwnProperty("imbalance")) {
                if (properties.payload === 1)
                    return "payload: multiple values";
                properties.payload = 1;
                {
                    let error = $root.market.Imbalance.verify(message.imbalance);
                    if (error)
                        return "imbalance." + error;
                }
            }
            if (message.absorption != null && message.hasOwnProperty("absorption")) {
                if (properties.payload === 1)
                    return "payload: multiple values";
                properties.payload = 1;
                {
                    let error = $root.market.Absorption.verify(message.absorption);
                    if (error)
                        return "absorption." + error;
                }
            }
            if (message.deltaFlip != null && message.hasOwnProperty("deltaFlip")) {
                if (properties.payload === 1)
                    return "payload: multiple values";
                properties.payload = 1;
                {
                    let error = $root.market.DeltaFlip.verify(message.deltaFlip);
                    if (error)
                        return "deltaFlip." + error;
                }
            }
            if (message.largeTrade != null && message.hasOwnProperty("largeTrade")) {
                if (properties.payload === 1)
                    return "payload: multiple values";
                properties.payload = 1;
                {
                    let error = $root.market.LargeTrade.verify(message.largeTrade);
                    if (error)
                        return "largeTrade." + error;
                }
            }
            if (message.optionTrade != null && message.hasOwnProperty("optionTrade")) {
                if (properties.payload === 1)
                    return "payload: multiple values";
                properties.payload = 1;
                {
                    let error = $root.market.OptionTrade.verify(message.optionTrade);
                    if (error)
                        return "optionTrade." + error;
                }
            }
            if (message.heartbeat != null && message.hasOwnProperty("heartbeat")) {
                if (properties.payload === 1)
                    return "payload: multiple values";
                properties.payload = 1;
                {
                    let error = $root.market.Heartbeat.verify(message.heartbeat);
                    if (error)
                        return "heartbeat." + error;
                }
            }
            if (message.external != null && message.hasOwnProperty("external")) {
                if (properties.payload === 1)
                    return "payload: multiple values";
                properties.payload = 1;
                {
                    let error = $root.market.ExternalJson.verify(message.external);
                    if (error)
                        return "external." + error;
                }
            }
            return null;
        };

        /**
         * Creates a MarketMessage message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof market.MarketMessage
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {market.MarketMessage} MarketMessage
         */
        MarketMessage.fromObject = function fromObject(object) {
            if (object instanceof $root.market.MarketMessage)
                return object;
            let message = new $root.market.MarketMessage();
            if (object.tick != null) {
                if (typeof object.tick !== "object")
                    throw TypeError(".market.MarketMessage.tick: object expected");
                message.tick = $root.market.Tick.fromObject(object.tick);
            }
            if (object.quote != null) {
                if (typeof object.quote !== "object")
                    throw TypeError(".market.MarketMessage.quote: object expected");
                message.quote = $root.market.Quote.fromObject(object.quote);
            }
            if (object.candle != null) {
                if (typeof object.candle !== "object")
                    throw TypeError(".market.MarketMessage.candle: object expected");
                message.candle = $root.market.Candle.fromObject(object.candle);
            }
            if (object.cvd != null) {
                if (typeof object.cvd !== "object")
                    throw TypeError(".market.MarketMessage.cvd: object expected");
                message.cvd = $root.market.Cvd.fromObject(object.cvd);
            }
            if (object.footprint != null) {
                if (typeof object.footprint !== "object")
                    throw TypeError(".market.MarketMessage.footprint: object expected");
                message.footprint = $root.market.Footprint.fromObject(object.footprint);
            }
            if (object.sweep != null) {
                if (typeof object.sweep !== "object")
                    throw TypeError(".market.MarketMessage.sweep: object expected");
                message.sweep = $root.market.Sweep.fromObject(object.sweep);
            }
            if (object.imbalance != null) {
                if (typeof object.imbalance !== "object")
                    throw TypeError(".market.MarketMessage.imbalance: object expected");
                message.imbalance = $root.market.Imbalance.fromObject(object.imbalance);
            }
            if (object.absorption != null) {
                if (typeof object.absorption !== "object")
                    throw TypeError(".market.MarketMessage.absorption: object expected");
                message.absorption = $root.market.Absorption.fromObject(object.absorption);
            }
            if (object.deltaFlip != null) {
                if (typeof object.deltaFlip !== "object")
                    throw TypeError(".market.MarketMessage.deltaFlip: object expected");
                message.deltaFlip = $root.market.DeltaFlip.fromObject(object.deltaFlip);
            }
            if (object.largeTrade != null) {
                if (typeof object.largeTrade !== "object")
                    throw TypeError(".market.MarketMessage.largeTrade: object expected");
                message.largeTrade = $root.market.LargeTrade.fromObject(object.largeTrade);
            }
            if (object.optionTrade != null) {
                if (typeof object.optionTrade !== "object")
                    throw TypeError(".market.MarketMessage.optionTrade: object expected");
                message.optionTrade = $root.market.OptionTrade.fromObject(object.optionTrade);
            }
            if (object.heartbeat != null) {
                if (typeof object.heartbeat !== "object")
                    throw TypeError(".market.MarketMessage.heartbeat: object expected");
                message.heartbeat = $root.market.Heartbeat.fromObject(object.heartbeat);
            }
            if (object.external != null) {
                if (typeof object.external !== "object")
                    throw TypeError(".market.MarketMessage.external: object expected");
                message.external = $root.market.ExternalJson.fromObject(object.external);
            }
            return message;
        };

        /**
         * Creates a plain object from a MarketMessage message. Also converts values to other types if specified.
         * @function toObject
         * @memberof market.MarketMessage
         * @static
         * @param {market.MarketMessage} message MarketMessage
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        MarketMessage.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (message.tick != null && message.hasOwnProperty("tick")) {
                object.tick = $root.market.Tick.toObject(message.tick, options);
                if (options.oneofs)
                    object.payload = "tick";
            }
            if (message.quote != null && message.hasOwnProperty("quote")) {
                object.quote = $root.market.Quote.toObject(message.quote, options);
                if (options.oneofs)
                    object.payload = "quote";
            }
            if (message.candle != null && message.hasOwnProperty("candle")) {
                object.candle = $root.market.Candle.toObject(message.candle, options);
                if (options.oneofs)
                    object.payload = "candle";
            }
            if (message.cvd != null && message.hasOwnProperty("cvd")) {
                object.cvd = $root.market.Cvd.toObject(message.cvd, options);
                if (options.oneofs)
                    object.payload = "cvd";
            }
            if (message.footprint != null && message.hasOwnProperty("footprint")) {
                object.footprint = $root.market.Footprint.toObject(message.footprint, options);
                if (options.oneofs)
                    object.payload = "footprint";
            }
            if (message.sweep != null && message.hasOwnProperty("sweep")) {
                object.sweep = $root.market.Sweep.toObject(message.sweep, options);
                if (options.oneofs)
                    object.payload = "sweep";
            }
            if (message.imbalance != null && message.hasOwnProperty("imbalance")) {
                object.imbalance = $root.market.Imbalance.toObject(message.imbalance, options);
                if (options.oneofs)
                    object.payload = "imbalance";
            }
            if (message.absorption != null && message.hasOwnProperty("absorption")) {
                object.absorption = $root.market.Absorption.toObject(message.absorption, options);
                if (options.oneofs)
                    object.payload = "absorption";
            }
            if (message.deltaFlip != null && message.hasOwnProperty("deltaFlip")) {
                object.deltaFlip = $root.market.DeltaFlip.toObject(message.deltaFlip, options);
                if (options.oneofs)
                    object.payload = "deltaFlip";
            }
            if (message.largeTrade != null && message.hasOwnProperty("largeTrade")) {
                object.largeTrade = $root.market.LargeTrade.toObject(message.largeTrade, options);
                if (options.oneofs)
                    object.payload = "largeTrade";
            }
            if (message.optionTrade != null && message.hasOwnProperty("optionTrade")) {
                object.optionTrade = $root.market.OptionTrade.toObject(message.optionTrade, options);
                if (options.oneofs)
                    object.payload = "optionTrade";
            }
            if (message.heartbeat != null && message.hasOwnProperty("heartbeat")) {
                object.heartbeat = $root.market.Heartbeat.toObject(message.heartbeat, options);
                if (options.oneofs)
                    object.payload = "heartbeat";
            }
            if (message.external != null && message.hasOwnProperty("external")) {
                object.external = $root.market.ExternalJson.toObject(message.external, options);
                if (options.oneofs)
                    object.payload = "external";
            }
            return object;
        };

        /**
         * Converts this MarketMessage to JSON.
         * @function toJSON
         * @memberof market.MarketMessage
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        MarketMessage.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for MarketMessage
         * @function getTypeUrl
         * @memberof market.MarketMessage
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        MarketMessage.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/market.MarketMessage";
        };

        return MarketMessage;
    })();

    return market;
})();

export { $root as default };
