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

    market.Tick = (function() {

        /**
         * Properties of a Tick.
         * @memberof market
         * @interface ITick
         * @property {number|null} [price] Tick price
         * @property {number|Long|null} [size] Tick size
         * @property {string|null} [side] Tick side
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
        Tick.prototype.size = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * Tick side.
         * @member {string} side
         * @memberof market.Tick
         * @instance
         */
        Tick.prototype.side = "";

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
                writer.uint32(/* id 2, wireType 0 =*/16).int64(message.size);
            if (message.side != null && Object.hasOwnProperty.call(message, "side"))
                writer.uint32(/* id 3, wireType 2 =*/26).string(message.side);
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
                        message.size = reader.int64();
                        break;
                    }
                case 3: {
                        message.side = reader.string();
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
                if (!$util.isString(message.side))
                    return "side: string expected";
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
                    (message.size = $util.Long.fromValue(object.size)).unsigned = false;
                else if (typeof object.size === "string")
                    message.size = parseInt(object.size, 10);
                else if (typeof object.size === "number")
                    message.size = object.size;
                else if (typeof object.size === "object")
                    message.size = new $util.LongBits(object.size.low >>> 0, object.size.high >>> 0).toNumber();
            if (object.side != null)
                message.side = String(object.side);
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
                    let long = new $util.Long(0, 0, false);
                    object.size = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.size = options.longs === String ? "0" : 0;
                object.side = "";
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
                    object.size = options.longs === String ? $util.Long.prototype.toString.call(message.size) : options.longs === Number ? new $util.LongBits(message.size.low >>> 0, message.size.high >>> 0).toNumber() : message.size;
            if (message.side != null && message.hasOwnProperty("side"))
                object.side = message.side;
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
        Candle.prototype.volume = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * Candle timestamp.
         * @member {number|Long} timestamp
         * @memberof market.Candle
         * @instance
         */
        Candle.prototype.timestamp = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

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
                writer.uint32(/* id 5, wireType 0 =*/40).int64(message.volume);
            if (message.timestamp != null && Object.hasOwnProperty.call(message, "timestamp"))
                writer.uint32(/* id 6, wireType 0 =*/48).int64(message.timestamp);
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
                        message.volume = reader.int64();
                        break;
                    }
                case 6: {
                        message.timestamp = reader.int64();
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
                    (message.volume = $util.Long.fromValue(object.volume)).unsigned = false;
                else if (typeof object.volume === "string")
                    message.volume = parseInt(object.volume, 10);
                else if (typeof object.volume === "number")
                    message.volume = object.volume;
                else if (typeof object.volume === "object")
                    message.volume = new $util.LongBits(object.volume.low >>> 0, object.volume.high >>> 0).toNumber();
            if (object.timestamp != null)
                if ($util.Long)
                    (message.timestamp = $util.Long.fromValue(object.timestamp)).unsigned = false;
                else if (typeof object.timestamp === "string")
                    message.timestamp = parseInt(object.timestamp, 10);
                else if (typeof object.timestamp === "number")
                    message.timestamp = object.timestamp;
                else if (typeof object.timestamp === "object")
                    message.timestamp = new $util.LongBits(object.timestamp.low >>> 0, object.timestamp.high >>> 0).toNumber();
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
                    let long = new $util.Long(0, 0, false);
                    object.volume = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.volume = options.longs === String ? "0" : 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.timestamp = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.timestamp = options.longs === String ? "0" : 0;
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
                    object.volume = options.longs === String ? $util.Long.prototype.toString.call(message.volume) : options.longs === Number ? new $util.LongBits(message.volume.low >>> 0, message.volume.high >>> 0).toNumber() : message.volume;
            if (message.timestamp != null && message.hasOwnProperty("timestamp"))
                if (typeof message.timestamp === "number")
                    object.timestamp = options.longs === String ? String(message.timestamp) : message.timestamp;
                else
                    object.timestamp = options.longs === String ? $util.Long.prototype.toString.call(message.timestamp) : options.longs === Number ? new $util.LongBits(message.timestamp.low >>> 0, message.timestamp.high >>> 0).toNumber() : message.timestamp;
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
        Quote.prototype.bidSize = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * Quote askSize.
         * @member {number|Long} askSize
         * @memberof market.Quote
         * @instance
         */
        Quote.prototype.askSize = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * Quote timestampMs.
         * @member {number|Long} timestampMs
         * @memberof market.Quote
         * @instance
         */
        Quote.prototype.timestampMs = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

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
                writer.uint32(/* id 3, wireType 0 =*/24).int64(message.bidSize);
            if (message.askSize != null && Object.hasOwnProperty.call(message, "askSize"))
                writer.uint32(/* id 4, wireType 0 =*/32).int64(message.askSize);
            if (message.timestampMs != null && Object.hasOwnProperty.call(message, "timestampMs"))
                writer.uint32(/* id 5, wireType 0 =*/40).int64(message.timestampMs);
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
                        message.bidSize = reader.int64();
                        break;
                    }
                case 4: {
                        message.askSize = reader.int64();
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
                    (message.bidSize = $util.Long.fromValue(object.bidSize)).unsigned = false;
                else if (typeof object.bidSize === "string")
                    message.bidSize = parseInt(object.bidSize, 10);
                else if (typeof object.bidSize === "number")
                    message.bidSize = object.bidSize;
                else if (typeof object.bidSize === "object")
                    message.bidSize = new $util.LongBits(object.bidSize.low >>> 0, object.bidSize.high >>> 0).toNumber();
            if (object.askSize != null)
                if ($util.Long)
                    (message.askSize = $util.Long.fromValue(object.askSize)).unsigned = false;
                else if (typeof object.askSize === "string")
                    message.askSize = parseInt(object.askSize, 10);
                else if (typeof object.askSize === "number")
                    message.askSize = object.askSize;
                else if (typeof object.askSize === "object")
                    message.askSize = new $util.LongBits(object.askSize.low >>> 0, object.askSize.high >>> 0).toNumber();
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
                    let long = new $util.Long(0, 0, false);
                    object.bidSize = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.bidSize = options.longs === String ? "0" : 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.askSize = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.askSize = options.longs === String ? "0" : 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.timestampMs = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.timestampMs = options.longs === String ? "0" : 0;
            }
            if (message.bid != null && message.hasOwnProperty("bid"))
                object.bid = options.json && !isFinite(message.bid) ? String(message.bid) : message.bid;
            if (message.ask != null && message.hasOwnProperty("ask"))
                object.ask = options.json && !isFinite(message.ask) ? String(message.ask) : message.ask;
            if (message.bidSize != null && message.hasOwnProperty("bidSize"))
                if (typeof message.bidSize === "number")
                    object.bidSize = options.longs === String ? String(message.bidSize) : message.bidSize;
                else
                    object.bidSize = options.longs === String ? $util.Long.prototype.toString.call(message.bidSize) : options.longs === Number ? new $util.LongBits(message.bidSize.low >>> 0, message.bidSize.high >>> 0).toNumber() : message.bidSize;
            if (message.askSize != null && message.hasOwnProperty("askSize"))
                if (typeof message.askSize === "number")
                    object.askSize = options.longs === String ? String(message.askSize) : message.askSize;
                else
                    object.askSize = options.longs === String ? $util.Long.prototype.toString.call(message.askSize) : options.longs === Number ? new $util.LongBits(message.askSize.low >>> 0, message.askSize.high >>> 0).toNumber() : message.askSize;
            if (message.timestampMs != null && message.hasOwnProperty("timestampMs"))
                if (typeof message.timestampMs === "number")
                    object.timestampMs = options.longs === String ? String(message.timestampMs) : message.timestampMs;
                else
                    object.timestampMs = options.longs === String ? $util.Long.prototype.toString.call(message.timestampMs) : options.longs === Number ? new $util.LongBits(message.timestampMs.low >>> 0, message.timestampMs.high >>> 0).toNumber() : message.timestampMs;
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

    market.FlowEvent = (function() {

        /**
         * Properties of a FlowEvent.
         * @memberof market
         * @interface IFlowEvent
         * @property {string|null} [type] FlowEvent type
         * @property {market.ITick|null} [tick] FlowEvent tick
         * @property {market.ISweepEvent|null} [sweep] FlowEvent sweep
         * @property {market.IAbsorptionEvent|null} [absorption] FlowEvent absorption
         */

        /**
         * Constructs a new FlowEvent.
         * @memberof market
         * @classdesc Represents a FlowEvent.
         * @implements IFlowEvent
         * @constructor
         * @param {market.IFlowEvent=} [properties] Properties to set
         */
        function FlowEvent(properties) {
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * FlowEvent type.
         * @member {string} type
         * @memberof market.FlowEvent
         * @instance
         */
        FlowEvent.prototype.type = "";

        /**
         * FlowEvent tick.
         * @member {market.ITick|null|undefined} tick
         * @memberof market.FlowEvent
         * @instance
         */
        FlowEvent.prototype.tick = null;

        /**
         * FlowEvent sweep.
         * @member {market.ISweepEvent|null|undefined} sweep
         * @memberof market.FlowEvent
         * @instance
         */
        FlowEvent.prototype.sweep = null;

        /**
         * FlowEvent absorption.
         * @member {market.IAbsorptionEvent|null|undefined} absorption
         * @memberof market.FlowEvent
         * @instance
         */
        FlowEvent.prototype.absorption = null;

        /**
         * Creates a new FlowEvent instance using the specified properties.
         * @function create
         * @memberof market.FlowEvent
         * @static
         * @param {market.IFlowEvent=} [properties] Properties to set
         * @returns {market.FlowEvent} FlowEvent instance
         */
        FlowEvent.create = function create(properties) {
            return new FlowEvent(properties);
        };

        /**
         * Encodes the specified FlowEvent message. Does not implicitly {@link market.FlowEvent.verify|verify} messages.
         * @function encode
         * @memberof market.FlowEvent
         * @static
         * @param {market.IFlowEvent} message FlowEvent message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        FlowEvent.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.type != null && Object.hasOwnProperty.call(message, "type"))
                writer.uint32(/* id 1, wireType 2 =*/10).string(message.type);
            if (message.tick != null && Object.hasOwnProperty.call(message, "tick"))
                $root.market.Tick.encode(message.tick, writer.uint32(/* id 2, wireType 2 =*/18).fork()).ldelim();
            if (message.sweep != null && Object.hasOwnProperty.call(message, "sweep"))
                $root.market.SweepEvent.encode(message.sweep, writer.uint32(/* id 3, wireType 2 =*/26).fork()).ldelim();
            if (message.absorption != null && Object.hasOwnProperty.call(message, "absorption"))
                $root.market.AbsorptionEvent.encode(message.absorption, writer.uint32(/* id 4, wireType 2 =*/34).fork()).ldelim();
            return writer;
        };

        /**
         * Encodes the specified FlowEvent message, length delimited. Does not implicitly {@link market.FlowEvent.verify|verify} messages.
         * @function encodeDelimited
         * @memberof market.FlowEvent
         * @static
         * @param {market.IFlowEvent} message FlowEvent message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        FlowEvent.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a FlowEvent message from the specified reader or buffer.
         * @function decode
         * @memberof market.FlowEvent
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {market.FlowEvent} FlowEvent
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        FlowEvent.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.market.FlowEvent();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.type = reader.string();
                        break;
                    }
                case 2: {
                        message.tick = $root.market.Tick.decode(reader, reader.uint32());
                        break;
                    }
                case 3: {
                        message.sweep = $root.market.SweepEvent.decode(reader, reader.uint32());
                        break;
                    }
                case 4: {
                        message.absorption = $root.market.AbsorptionEvent.decode(reader, reader.uint32());
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
         * Decodes a FlowEvent message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof market.FlowEvent
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {market.FlowEvent} FlowEvent
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        FlowEvent.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a FlowEvent message.
         * @function verify
         * @memberof market.FlowEvent
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        FlowEvent.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.type != null && message.hasOwnProperty("type"))
                if (!$util.isString(message.type))
                    return "type: string expected";
            if (message.tick != null && message.hasOwnProperty("tick")) {
                let error = $root.market.Tick.verify(message.tick);
                if (error)
                    return "tick." + error;
            }
            if (message.sweep != null && message.hasOwnProperty("sweep")) {
                let error = $root.market.SweepEvent.verify(message.sweep);
                if (error)
                    return "sweep." + error;
            }
            if (message.absorption != null && message.hasOwnProperty("absorption")) {
                let error = $root.market.AbsorptionEvent.verify(message.absorption);
                if (error)
                    return "absorption." + error;
            }
            return null;
        };

        /**
         * Creates a FlowEvent message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof market.FlowEvent
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {market.FlowEvent} FlowEvent
         */
        FlowEvent.fromObject = function fromObject(object) {
            if (object instanceof $root.market.FlowEvent)
                return object;
            let message = new $root.market.FlowEvent();
            if (object.type != null)
                message.type = String(object.type);
            if (object.tick != null) {
                if (typeof object.tick !== "object")
                    throw TypeError(".market.FlowEvent.tick: object expected");
                message.tick = $root.market.Tick.fromObject(object.tick);
            }
            if (object.sweep != null) {
                if (typeof object.sweep !== "object")
                    throw TypeError(".market.FlowEvent.sweep: object expected");
                message.sweep = $root.market.SweepEvent.fromObject(object.sweep);
            }
            if (object.absorption != null) {
                if (typeof object.absorption !== "object")
                    throw TypeError(".market.FlowEvent.absorption: object expected");
                message.absorption = $root.market.AbsorptionEvent.fromObject(object.absorption);
            }
            return message;
        };

        /**
         * Creates a plain object from a FlowEvent message. Also converts values to other types if specified.
         * @function toObject
         * @memberof market.FlowEvent
         * @static
         * @param {market.FlowEvent} message FlowEvent
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        FlowEvent.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.defaults) {
                object.type = "";
                object.tick = null;
                object.sweep = null;
                object.absorption = null;
            }
            if (message.type != null && message.hasOwnProperty("type"))
                object.type = message.type;
            if (message.tick != null && message.hasOwnProperty("tick"))
                object.tick = $root.market.Tick.toObject(message.tick, options);
            if (message.sweep != null && message.hasOwnProperty("sweep"))
                object.sweep = $root.market.SweepEvent.toObject(message.sweep, options);
            if (message.absorption != null && message.hasOwnProperty("absorption"))
                object.absorption = $root.market.AbsorptionEvent.toObject(message.absorption, options);
            return object;
        };

        /**
         * Converts this FlowEvent to JSON.
         * @function toJSON
         * @memberof market.FlowEvent
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        FlowEvent.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for FlowEvent
         * @function getTypeUrl
         * @memberof market.FlowEvent
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        FlowEvent.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/market.FlowEvent";
        };

        return FlowEvent;
    })();

    market.SweepEvent = (function() {

        /**
         * Properties of a SweepEvent.
         * @memberof market
         * @interface ISweepEvent
         * @property {string|null} [direction] SweepEvent direction
         * @property {number|null} [notional] SweepEvent notional
         * @property {Array.<number>|null} [strikes] SweepEvent strikes
         */

        /**
         * Constructs a new SweepEvent.
         * @memberof market
         * @classdesc Represents a SweepEvent.
         * @implements ISweepEvent
         * @constructor
         * @param {market.ISweepEvent=} [properties] Properties to set
         */
        function SweepEvent(properties) {
            this.strikes = [];
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * SweepEvent direction.
         * @member {string} direction
         * @memberof market.SweepEvent
         * @instance
         */
        SweepEvent.prototype.direction = "";

        /**
         * SweepEvent notional.
         * @member {number} notional
         * @memberof market.SweepEvent
         * @instance
         */
        SweepEvent.prototype.notional = 0;

        /**
         * SweepEvent strikes.
         * @member {Array.<number>} strikes
         * @memberof market.SweepEvent
         * @instance
         */
        SweepEvent.prototype.strikes = $util.emptyArray;

        /**
         * Creates a new SweepEvent instance using the specified properties.
         * @function create
         * @memberof market.SweepEvent
         * @static
         * @param {market.ISweepEvent=} [properties] Properties to set
         * @returns {market.SweepEvent} SweepEvent instance
         */
        SweepEvent.create = function create(properties) {
            return new SweepEvent(properties);
        };

        /**
         * Encodes the specified SweepEvent message. Does not implicitly {@link market.SweepEvent.verify|verify} messages.
         * @function encode
         * @memberof market.SweepEvent
         * @static
         * @param {market.ISweepEvent} message SweepEvent message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        SweepEvent.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.direction != null && Object.hasOwnProperty.call(message, "direction"))
                writer.uint32(/* id 1, wireType 2 =*/10).string(message.direction);
            if (message.notional != null && Object.hasOwnProperty.call(message, "notional"))
                writer.uint32(/* id 2, wireType 1 =*/17).double(message.notional);
            if (message.strikes != null && message.strikes.length) {
                writer.uint32(/* id 3, wireType 2 =*/26).fork();
                for (let i = 0; i < message.strikes.length; ++i)
                    writer.double(message.strikes[i]);
                writer.ldelim();
            }
            return writer;
        };

        /**
         * Encodes the specified SweepEvent message, length delimited. Does not implicitly {@link market.SweepEvent.verify|verify} messages.
         * @function encodeDelimited
         * @memberof market.SweepEvent
         * @static
         * @param {market.ISweepEvent} message SweepEvent message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        SweepEvent.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a SweepEvent message from the specified reader or buffer.
         * @function decode
         * @memberof market.SweepEvent
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {market.SweepEvent} SweepEvent
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        SweepEvent.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.market.SweepEvent();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.direction = reader.string();
                        break;
                    }
                case 2: {
                        message.notional = reader.double();
                        break;
                    }
                case 3: {
                        if (!(message.strikes && message.strikes.length))
                            message.strikes = [];
                        if ((tag & 7) === 2) {
                            let end2 = reader.uint32() + reader.pos;
                            while (reader.pos < end2)
                                message.strikes.push(reader.double());
                        } else
                            message.strikes.push(reader.double());
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
         * Decodes a SweepEvent message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof market.SweepEvent
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {market.SweepEvent} SweepEvent
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        SweepEvent.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a SweepEvent message.
         * @function verify
         * @memberof market.SweepEvent
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        SweepEvent.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.direction != null && message.hasOwnProperty("direction"))
                if (!$util.isString(message.direction))
                    return "direction: string expected";
            if (message.notional != null && message.hasOwnProperty("notional"))
                if (typeof message.notional !== "number")
                    return "notional: number expected";
            if (message.strikes != null && message.hasOwnProperty("strikes")) {
                if (!Array.isArray(message.strikes))
                    return "strikes: array expected";
                for (let i = 0; i < message.strikes.length; ++i)
                    if (typeof message.strikes[i] !== "number")
                        return "strikes: number[] expected";
            }
            return null;
        };

        /**
         * Creates a SweepEvent message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof market.SweepEvent
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {market.SweepEvent} SweepEvent
         */
        SweepEvent.fromObject = function fromObject(object) {
            if (object instanceof $root.market.SweepEvent)
                return object;
            let message = new $root.market.SweepEvent();
            if (object.direction != null)
                message.direction = String(object.direction);
            if (object.notional != null)
                message.notional = Number(object.notional);
            if (object.strikes) {
                if (!Array.isArray(object.strikes))
                    throw TypeError(".market.SweepEvent.strikes: array expected");
                message.strikes = [];
                for (let i = 0; i < object.strikes.length; ++i)
                    message.strikes[i] = Number(object.strikes[i]);
            }
            return message;
        };

        /**
         * Creates a plain object from a SweepEvent message. Also converts values to other types if specified.
         * @function toObject
         * @memberof market.SweepEvent
         * @static
         * @param {market.SweepEvent} message SweepEvent
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        SweepEvent.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.arrays || options.defaults)
                object.strikes = [];
            if (options.defaults) {
                object.direction = "";
                object.notional = 0;
            }
            if (message.direction != null && message.hasOwnProperty("direction"))
                object.direction = message.direction;
            if (message.notional != null && message.hasOwnProperty("notional"))
                object.notional = options.json && !isFinite(message.notional) ? String(message.notional) : message.notional;
            if (message.strikes && message.strikes.length) {
                object.strikes = [];
                for (let j = 0; j < message.strikes.length; ++j)
                    object.strikes[j] = options.json && !isFinite(message.strikes[j]) ? String(message.strikes[j]) : message.strikes[j];
            }
            return object;
        };

        /**
         * Converts this SweepEvent to JSON.
         * @function toJSON
         * @memberof market.SweepEvent
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        SweepEvent.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for SweepEvent
         * @function getTypeUrl
         * @memberof market.SweepEvent
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        SweepEvent.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/market.SweepEvent";
        };

        return SweepEvent;
    })();

    market.AbsorptionEvent = (function() {

        /**
         * Properties of an AbsorptionEvent.
         * @memberof market
         * @interface IAbsorptionEvent
         * @property {number|null} [price] AbsorptionEvent price
         * @property {string|null} [direction] AbsorptionEvent direction
         * @property {number|Long|null} [volume] AbsorptionEvent volume
         */

        /**
         * Constructs a new AbsorptionEvent.
         * @memberof market
         * @classdesc Represents an AbsorptionEvent.
         * @implements IAbsorptionEvent
         * @constructor
         * @param {market.IAbsorptionEvent=} [properties] Properties to set
         */
        function AbsorptionEvent(properties) {
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * AbsorptionEvent price.
         * @member {number} price
         * @memberof market.AbsorptionEvent
         * @instance
         */
        AbsorptionEvent.prototype.price = 0;

        /**
         * AbsorptionEvent direction.
         * @member {string} direction
         * @memberof market.AbsorptionEvent
         * @instance
         */
        AbsorptionEvent.prototype.direction = "";

        /**
         * AbsorptionEvent volume.
         * @member {number|Long} volume
         * @memberof market.AbsorptionEvent
         * @instance
         */
        AbsorptionEvent.prototype.volume = $util.Long ? $util.Long.fromBits(0,0,false) : 0;

        /**
         * Creates a new AbsorptionEvent instance using the specified properties.
         * @function create
         * @memberof market.AbsorptionEvent
         * @static
         * @param {market.IAbsorptionEvent=} [properties] Properties to set
         * @returns {market.AbsorptionEvent} AbsorptionEvent instance
         */
        AbsorptionEvent.create = function create(properties) {
            return new AbsorptionEvent(properties);
        };

        /**
         * Encodes the specified AbsorptionEvent message. Does not implicitly {@link market.AbsorptionEvent.verify|verify} messages.
         * @function encode
         * @memberof market.AbsorptionEvent
         * @static
         * @param {market.IAbsorptionEvent} message AbsorptionEvent message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        AbsorptionEvent.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.price != null && Object.hasOwnProperty.call(message, "price"))
                writer.uint32(/* id 1, wireType 1 =*/9).double(message.price);
            if (message.direction != null && Object.hasOwnProperty.call(message, "direction"))
                writer.uint32(/* id 2, wireType 2 =*/18).string(message.direction);
            if (message.volume != null && Object.hasOwnProperty.call(message, "volume"))
                writer.uint32(/* id 3, wireType 0 =*/24).int64(message.volume);
            return writer;
        };

        /**
         * Encodes the specified AbsorptionEvent message, length delimited. Does not implicitly {@link market.AbsorptionEvent.verify|verify} messages.
         * @function encodeDelimited
         * @memberof market.AbsorptionEvent
         * @static
         * @param {market.IAbsorptionEvent} message AbsorptionEvent message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        AbsorptionEvent.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes an AbsorptionEvent message from the specified reader or buffer.
         * @function decode
         * @memberof market.AbsorptionEvent
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {market.AbsorptionEvent} AbsorptionEvent
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        AbsorptionEvent.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.market.AbsorptionEvent();
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
                        message.direction = reader.string();
                        break;
                    }
                case 3: {
                        message.volume = reader.int64();
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
         * Decodes an AbsorptionEvent message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof market.AbsorptionEvent
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {market.AbsorptionEvent} AbsorptionEvent
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        AbsorptionEvent.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies an AbsorptionEvent message.
         * @function verify
         * @memberof market.AbsorptionEvent
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        AbsorptionEvent.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.price != null && message.hasOwnProperty("price"))
                if (typeof message.price !== "number")
                    return "price: number expected";
            if (message.direction != null && message.hasOwnProperty("direction"))
                if (!$util.isString(message.direction))
                    return "direction: string expected";
            if (message.volume != null && message.hasOwnProperty("volume"))
                if (!$util.isInteger(message.volume) && !(message.volume && $util.isInteger(message.volume.low) && $util.isInteger(message.volume.high)))
                    return "volume: integer|Long expected";
            return null;
        };

        /**
         * Creates an AbsorptionEvent message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof market.AbsorptionEvent
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {market.AbsorptionEvent} AbsorptionEvent
         */
        AbsorptionEvent.fromObject = function fromObject(object) {
            if (object instanceof $root.market.AbsorptionEvent)
                return object;
            let message = new $root.market.AbsorptionEvent();
            if (object.price != null)
                message.price = Number(object.price);
            if (object.direction != null)
                message.direction = String(object.direction);
            if (object.volume != null)
                if ($util.Long)
                    (message.volume = $util.Long.fromValue(object.volume)).unsigned = false;
                else if (typeof object.volume === "string")
                    message.volume = parseInt(object.volume, 10);
                else if (typeof object.volume === "number")
                    message.volume = object.volume;
                else if (typeof object.volume === "object")
                    message.volume = new $util.LongBits(object.volume.low >>> 0, object.volume.high >>> 0).toNumber();
            return message;
        };

        /**
         * Creates a plain object from an AbsorptionEvent message. Also converts values to other types if specified.
         * @function toObject
         * @memberof market.AbsorptionEvent
         * @static
         * @param {market.AbsorptionEvent} message AbsorptionEvent
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        AbsorptionEvent.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.defaults) {
                object.price = 0;
                object.direction = "";
                if ($util.Long) {
                    let long = new $util.Long(0, 0, false);
                    object.volume = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.volume = options.longs === String ? "0" : 0;
            }
            if (message.price != null && message.hasOwnProperty("price"))
                object.price = options.json && !isFinite(message.price) ? String(message.price) : message.price;
            if (message.direction != null && message.hasOwnProperty("direction"))
                object.direction = message.direction;
            if (message.volume != null && message.hasOwnProperty("volume"))
                if (typeof message.volume === "number")
                    object.volume = options.longs === String ? String(message.volume) : message.volume;
                else
                    object.volume = options.longs === String ? $util.Long.prototype.toString.call(message.volume) : options.longs === Number ? new $util.LongBits(message.volume.low >>> 0, message.volume.high >>> 0).toNumber() : message.volume;
            return object;
        };

        /**
         * Converts this AbsorptionEvent to JSON.
         * @function toJSON
         * @memberof market.AbsorptionEvent
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        AbsorptionEvent.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for AbsorptionEvent
         * @function getTypeUrl
         * @memberof market.AbsorptionEvent
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        AbsorptionEvent.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/market.AbsorptionEvent";
        };

        return AbsorptionEvent;
    })();

    market.MarketMessage = (function() {

        /**
         * Properties of a MarketMessage.
         * @memberof market
         * @interface IMarketMessage
         * @property {string|null} [event] MarketMessage event
         * @property {market.ITick|null} [tick] MarketMessage tick
         * @property {market.ICandle|null} [candle] MarketMessage candle
         * @property {market.IQuote|null} [quote] MarketMessage quote
         * @property {market.IFlowEvent|null} [flow] MarketMessage flow
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
         * MarketMessage event.
         * @member {string} event
         * @memberof market.MarketMessage
         * @instance
         */
        MarketMessage.prototype.event = "";

        /**
         * MarketMessage tick.
         * @member {market.ITick|null|undefined} tick
         * @memberof market.MarketMessage
         * @instance
         */
        MarketMessage.prototype.tick = null;

        /**
         * MarketMessage candle.
         * @member {market.ICandle|null|undefined} candle
         * @memberof market.MarketMessage
         * @instance
         */
        MarketMessage.prototype.candle = null;

        /**
         * MarketMessage quote.
         * @member {market.IQuote|null|undefined} quote
         * @memberof market.MarketMessage
         * @instance
         */
        MarketMessage.prototype.quote = null;

        /**
         * MarketMessage flow.
         * @member {market.IFlowEvent|null|undefined} flow
         * @memberof market.MarketMessage
         * @instance
         */
        MarketMessage.prototype.flow = null;

        // OneOf field names bound to virtual getters and setters
        let $oneOfFields;

        /**
         * MarketMessage payload.
         * @member {"tick"|"candle"|"quote"|"flow"|undefined} payload
         * @memberof market.MarketMessage
         * @instance
         */
        Object.defineProperty(MarketMessage.prototype, "payload", {
            get: $util.oneOfGetter($oneOfFields = ["tick", "candle", "quote", "flow"]),
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
            if (message.event != null && Object.hasOwnProperty.call(message, "event"))
                writer.uint32(/* id 1, wireType 2 =*/10).string(message.event);
            if (message.tick != null && Object.hasOwnProperty.call(message, "tick"))
                $root.market.Tick.encode(message.tick, writer.uint32(/* id 2, wireType 2 =*/18).fork()).ldelim();
            if (message.candle != null && Object.hasOwnProperty.call(message, "candle"))
                $root.market.Candle.encode(message.candle, writer.uint32(/* id 3, wireType 2 =*/26).fork()).ldelim();
            if (message.quote != null && Object.hasOwnProperty.call(message, "quote"))
                $root.market.Quote.encode(message.quote, writer.uint32(/* id 4, wireType 2 =*/34).fork()).ldelim();
            if (message.flow != null && Object.hasOwnProperty.call(message, "flow"))
                $root.market.FlowEvent.encode(message.flow, writer.uint32(/* id 5, wireType 2 =*/42).fork()).ldelim();
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
                        message.event = reader.string();
                        break;
                    }
                case 2: {
                        message.tick = $root.market.Tick.decode(reader, reader.uint32());
                        break;
                    }
                case 3: {
                        message.candle = $root.market.Candle.decode(reader, reader.uint32());
                        break;
                    }
                case 4: {
                        message.quote = $root.market.Quote.decode(reader, reader.uint32());
                        break;
                    }
                case 5: {
                        message.flow = $root.market.FlowEvent.decode(reader, reader.uint32());
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
            if (message.event != null && message.hasOwnProperty("event"))
                if (!$util.isString(message.event))
                    return "event: string expected";
            if (message.tick != null && message.hasOwnProperty("tick")) {
                properties.payload = 1;
                {
                    let error = $root.market.Tick.verify(message.tick);
                    if (error)
                        return "tick." + error;
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
            if (message.flow != null && message.hasOwnProperty("flow")) {
                if (properties.payload === 1)
                    return "payload: multiple values";
                properties.payload = 1;
                {
                    let error = $root.market.FlowEvent.verify(message.flow);
                    if (error)
                        return "flow." + error;
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
            if (object.event != null)
                message.event = String(object.event);
            if (object.tick != null) {
                if (typeof object.tick !== "object")
                    throw TypeError(".market.MarketMessage.tick: object expected");
                message.tick = $root.market.Tick.fromObject(object.tick);
            }
            if (object.candle != null) {
                if (typeof object.candle !== "object")
                    throw TypeError(".market.MarketMessage.candle: object expected");
                message.candle = $root.market.Candle.fromObject(object.candle);
            }
            if (object.quote != null) {
                if (typeof object.quote !== "object")
                    throw TypeError(".market.MarketMessage.quote: object expected");
                message.quote = $root.market.Quote.fromObject(object.quote);
            }
            if (object.flow != null) {
                if (typeof object.flow !== "object")
                    throw TypeError(".market.MarketMessage.flow: object expected");
                message.flow = $root.market.FlowEvent.fromObject(object.flow);
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
            if (options.defaults)
                object.event = "";
            if (message.event != null && message.hasOwnProperty("event"))
                object.event = message.event;
            if (message.tick != null && message.hasOwnProperty("tick")) {
                object.tick = $root.market.Tick.toObject(message.tick, options);
                if (options.oneofs)
                    object.payload = "tick";
            }
            if (message.candle != null && message.hasOwnProperty("candle")) {
                object.candle = $root.market.Candle.toObject(message.candle, options);
                if (options.oneofs)
                    object.payload = "candle";
            }
            if (message.quote != null && message.hasOwnProperty("quote")) {
                object.quote = $root.market.Quote.toObject(message.quote, options);
                if (options.oneofs)
                    object.payload = "quote";
            }
            if (message.flow != null && message.hasOwnProperty("flow")) {
                object.flow = $root.market.FlowEvent.toObject(message.flow, options);
                if (options.oneofs)
                    object.payload = "flow";
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
