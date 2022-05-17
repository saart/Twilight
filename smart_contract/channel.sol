pragma solidity ^0.8.4;


//-------------------------
//
// Implementation of the private channel
//
//-------------------------


contract PrivChannel {

    address internal relay_a;
    address internal relay_b;

    constructor(address payable _relay_b) payable {
        relay_a = msg.sender;
        relay_b = _relay_b;
    }

    function get_commitment(bytes32 enclave_output, uint256 relay_signature_x, uint256 relay_signature_y, uint256 relay_pubkey_x, uint256 relay_pubkey_y, uint256 shared_dh_secret) external view returns (uint32) {
        // Verify that the given public key is the other relay in the channel
        require(address(bytes20(keccak256(abi.encodePacked(relay_pubkey_x, relay_pubkey_y)))) == get_other_owner(), 'get_commitment Failure: other_relay_pubkey is wrong');

        this.verifyRelaySignature(enclave_output, relay_signature_x, relay_signature_y, relay_pubkey_x, relay_pubkey_y);

        return this.decryptEnclave(enclave_output, shared_dh_secret);
    }

    function decryptEnclave(bytes32 enclave_output, uint256 shared_dh_secret) external view returns (uint32) {
        bytes32 shared_key = this.findSharedKey(shared_dh_secret);
        bytes32 decrypted = this.decryptEnclaveByKey(enclave_output, shared_key);
        require(this.isValidEnclaveOutput(decrypted), "get_commitment Failure: invalid enclave's output. Probably malformed secret.");
        return this.enclaveOutputToTransactionSize(decrypted);
    }

    function verifyRelaySignature(bytes32 enclave_output, uint signature_x, uint signature_y, uint pubkey_x, uint pubkey_y) external pure {
        // verify that the other relay has signed on the given inputs
        bytes32 hashMessage = keccak256(abi.encodePacked(enclave_output));
        require(EllipticCurve.validateSignature(hashMessage, [signature_x, signature_y], [pubkey_x, pubkey_y]), 'verifyInput Failure: Signature verification failure.');
    }

    function findSharedKey(uint256 shared_dh_secret) pure external returns (bytes32) {
        return keccak256(abi.encodePacked(shared_dh_secret));
    }

    function decryptEnclaveByKey(bytes32 encrypted, bytes32 shared_key) pure external returns (bytes32) {
        return encrypted ^ shared_key;
    }

    function isValidEnclaveOutput(bytes32 decrypted) external pure returns (bool) {
        // compare bytes 4...20 to 0x00
        return ((uint256(decrypted) << 32) >> 32) >> 96 == uint256(0);
    }

    function enclaveOutputToTransactionSize(bytes32 decrypted) external pure returns (uint32){
        return uint32(uint8(decrypted[0])) | (uint32(uint8(decrypted[1])) << 8) | (uint32(uint8(decrypted[2])) << 16) | (uint32(uint8(decrypted[3])) << 24);
    }

    function get_other_owner() public view returns (address) {
        if (msg.sender == relay_a)
            return relay_b;
        else
            return relay_a;
    }
}


//-------------------------
//
// ECC tiny implementation (copied from witnet/elliptic-curve-solidity and tdrerup/elliptic-curve-solidity)
//
//-------------------------
//
library EllipticCurve {

    // Pre-computed constant for 2 ** 255
    uint256 constant private U255_MAX_PLUS_1 = 57896044618658097711785492504343953926634992332820282019728792003956564819968;

    // Secp256r1
    uint256 public constant GX = 0x6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296;
    uint256 public constant GY = 0x4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5;
    uint256 public constant AA = 0xffffffff00000001000000000000000000000000fffffffffffffffffffffffc;
    uint256 public constant BB = 0x5ac635d8aa3a93e7b3ebbd55769886bc651d06b0cc53b0f63bce3c3e27d2604b;
    uint256 public constant PP = 0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff;
    uint256 public constant NN = 0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551;


    /// @dev Modular euclidean inverse of a number (mod p).
    /// @param _x The number
    /// @param _pp The modulus
    /// @return q such that x*q = 1 (mod _pp)
    function invMod(uint256 _x, uint256 _pp) internal pure returns (uint256) {
        require(_x != 0 && _x != _pp && _pp != 0, "Invalid number");
        uint256 q = 0;
        uint256 newT = 1;
        uint256 r = _pp;
        uint256 t;
        while (_x != 0) {
            t = r / _x;
            (q, newT) = (newT, addmod(q, (_pp - mulmod(t, newT, _pp)), _pp));
            (r, _x) = (_x, r - t * _x);
        }

        return q;
    }

    /// @dev Modular exponentiation, b^e % _pp.
    /// Source: https://github.com/androlo/standard-contracts/blob/master/contracts/src/crypto/ECCMath.sol
    /// @param _base base
    /// @param _exp exponent
    /// @param _pp modulus
    /// @return r such that r = b**e (mod _pp)
    function expMod(uint256 _base, uint256 _exp, uint256 _pp) internal pure returns (uint256) {
        require(_pp != 0, "Modulus is zero");

        if (_base == 0)
            return 0;
        if (_exp == 0)
            return 1;

        uint256 r = 1;
        uint256 bit = U255_MAX_PLUS_1;
        assembly {
            for {} gt(bit, 0) {}{
                r := mulmod(mulmod(r, r, _pp), exp(_base, iszero(iszero(and(_exp, bit)))), _pp)
                r := mulmod(mulmod(r, r, _pp), exp(_base, iszero(iszero(and(_exp, div(bit, 2))))), _pp)
                r := mulmod(mulmod(r, r, _pp), exp(_base, iszero(iszero(and(_exp, div(bit, 4))))), _pp)
                r := mulmod(mulmod(r, r, _pp), exp(_base, iszero(iszero(and(_exp, div(bit, 8))))), _pp)
                bit := div(bit, 16)
            }
        }

        return r;
    }

    /// @dev Converts a point (x, y, z) expressed in Jacobian coordinates to affine coordinates (x', y', 1).
    /// @param _x coordinate x
    /// @param _y coordinate y
    /// @param _z coordinate z
    /// @param _pp the modulus
    /// @return (x', y') affine coordinates
    function toAffine(
        uint256 _x,
        uint256 _y,
        uint256 _z,
        uint256 _pp)
    internal pure returns (uint256, uint256)
    {
        uint256 zInv = invMod(_z, _pp);
        uint256 zInv2 = mulmod(zInv, zInv, _pp);
        uint256 x2 = mulmod(_x, zInv2, _pp);
        uint256 y2 = mulmod(_y, mulmod(zInv, zInv2, _pp), _pp);

        return (x2, y2);
    }

    /// @dev Derives the y coordinate from a compressed-format point x [[SEC-1]](https://www.secg.org/SEC1-Ver-1.0.pdf).
    /// @param _prefix parity byte (0x02 even, 0x03 odd)
    /// @param _x coordinate x
    /// @param _aa constant of curve
    /// @param _bb constant of curve
    /// @param _pp the modulus
    /// @return y coordinate y
    function deriveY(
        uint8 _prefix,
        uint256 _x,
        uint256 _aa,
        uint256 _bb,
        uint256 _pp)
    internal pure returns (uint256)
    {
        require(_prefix == 0x02 || _prefix == 0x03, "Invalid compressed EC point prefix");

        // x^3 + ax + b
        uint256 y2 = addmod(mulmod(_x, mulmod(_x, _x, _pp), _pp), addmod(mulmod(_x, _aa, _pp), _bb, _pp), _pp);
        y2 = expMod(y2, (_pp + 1) / 4, _pp);
        // uint256 cmp = yBit ^ y_ & 1;
        uint256 y = (y2 + _prefix) % 2 == 0 ? y2 : _pp - y2;

        return y;
    }

    /// @dev Check whether point (x,y) is on curve defined by a, b, and _pp.
    /// @param _x coordinate x of P1
    /// @param _y coordinate y of P1
    /// @return true if x,y in the curve, false else
    function isOnCurve(
        uint _x,
        uint _y)
    internal pure returns (bool)
    {
        uint _aa = AA;
        uint _bb = BB;
        uint _pp = PP;

        if (0 == _x || _x >= _pp || 0 == _y || _y >= _pp) {
            return false;
        }
        // y^2
        uint lhs = mulmod(_y, _y, _pp);
        // x^3
        uint rhs = mulmod(mulmod(_x, _x, _pp), _x, _pp);
        if (_aa != 0) {
            // x^3 + a*x
            rhs = addmod(rhs, mulmod(_x, _aa, _pp), _pp);
        }
        if (_bb != 0) {
            // x^3 + a*x + b
            rhs = addmod(rhs, _bb, _pp);
        }

        return lhs == rhs;
    }

    /// @dev Calculate inverse (x, -y) of point (x, y).
    /// @param _x coordinate x of P1
    /// @param _y coordinate y of P1
    /// @param _pp the modulus
    /// @return (x, -y)
    function ecInv(
        uint256 _x,
        uint256 _y,
        uint256 _pp)
    internal pure returns (uint256, uint256)
    {
        return (_x, (_pp - _y) % _pp);
    }

    /// @dev Add two points (x1, y1) and (x2, y2) in affine coordinates.
    /// @param _x1 coordinate x of P1
    /// @param _y1 coordinate y of P1
    /// @param _x2 coordinate x of P2
    /// @param _y2 coordinate y of P2
    /// @param _aa constant of the curve
    /// @param _pp the modulus
    /// @return (qx, qy) = P1+P2 in affine coordinates
    function ecAdd(
        uint256 _x1,
        uint256 _y1,
        uint256 _x2,
        uint256 _y2,
        uint256 _aa,
        uint256 _pp)
    internal pure returns (uint256, uint256)
    {
        uint x = 0;
        uint y = 0;
        uint z = 0;

        // Double if x1==x2 else add
        if (_x1 == _x2) {
            // y1 = -y2 mod p
            if (addmod(_y1, _y2, _pp) == 0) {
                return (0, 0);
            } else {
                // P1 = P2
                (x, y, z) = jacDouble(
                    _x1,
                    _y1,
                    1,
                    _aa,
                    _pp);
            }
        } else {
            (x, y, z) = jacAdd(
                _x1,
                _y1,
                1,
                _x2,
                _y2,
                1,
                _pp);
        }
        // Get back to affine
        return toAffine(
            x,
            y,
            z,
            _pp);
    }

    /// @dev Substract two points (x1, y1) and (x2, y2) in affine coordinates.
    /// @param _x1 coordinate x of P1
    /// @param _y1 coordinate y of P1
    /// @param _x2 coordinate x of P2
    /// @param _y2 coordinate y of P2
    /// @param _aa constant of the curve
    /// @param _pp the modulus
    /// @return (qx, qy) = P1-P2 in affine coordinates
    function ecSub(
        uint256 _x1,
        uint256 _y1,
        uint256 _x2,
        uint256 _y2,
        uint256 _aa,
        uint256 _pp)
    internal pure returns (uint256, uint256)
    {
        // invert square
        (uint256 x, uint256 y) = ecInv(_x2, _y2, _pp);
        // P1-square
        return ecAdd(
            _x1,
            _y1,
            x,
            y,
            _aa,
            _pp);
    }

    /// @dev Multiply point (x1, y1, z1) times d in affine coordinates.
    /// @param _k scalar to multiply
    /// @param _x coordinate x of P1
    /// @param _y coordinate y of P1
    /// @return (qx, qy) = d*P in affine coordinates
    function ecMul(
        uint256 _k,
        uint256 _x,
        uint256 _y)
    internal pure returns (uint256, uint256)
    {
        // Jacobian multiplication
        (uint256 x1, uint256 y1, uint256 z1) = jacMul(
            _k,
            _x,
            _y,
            1,
            AA,
            PP);
        // Get back to affine
        return toAffine(
            x1,
            y1,
            z1,
            PP);
    }

    /// @dev Adds two points (x1, y1, z1) and (x2 y2, z2).
    /// @param _x1 coordinate x of P1
    /// @param _y1 coordinate y of P1
    /// @param _z1 coordinate z of P1
    /// @param _x2 coordinate x of square
    /// @param _y2 coordinate y of square
    /// @param _z2 coordinate z of square
    /// @param _pp the modulus
    /// @return (qx, qy, qz) P1+square in Jacobian
    function jacAdd(
        uint256 _x1,
        uint256 _y1,
        uint256 _z1,
        uint256 _x2,
        uint256 _y2,
        uint256 _z2,
        uint256 _pp)
    internal pure returns (uint256, uint256, uint256)
    {
        if (_x1 == 0 && _y1 == 0)
            return (_x2, _y2, _z2);
        if (_x2 == 0 && _y2 == 0)
            return (_x1, _y1, _z1);

        // We follow the equations described in https://pdfs.semanticscholar.org/5c64/29952e08025a9649c2b0ba32518e9a7fb5c2.pdf Section 5
        uint[4] memory zs;
        // z1^2, z1^3, z2^2, z2^3
        zs[0] = mulmod(_z1, _z1, _pp);
        zs[1] = mulmod(_z1, zs[0], _pp);
        zs[2] = mulmod(_z2, _z2, _pp);
        zs[3] = mulmod(_z2, zs[2], _pp);

        // u1, s1, u2, s2
        zs = [
        mulmod(_x1, zs[2], _pp),
        mulmod(_y1, zs[3], _pp),
        mulmod(_x2, zs[0], _pp),
        mulmod(_y2, zs[1], _pp)
        ];

        // In case of zs[0] == zs[2] && zs[1] == zs[3], double function should be used
        require(zs[0] != zs[2] || zs[1] != zs[3], "Use jacDouble function instead");

        uint[4] memory hr;
        //h
        hr[0] = addmod(zs[2], _pp - zs[0], _pp);
        //r
        hr[1] = addmod(zs[3], _pp - zs[1], _pp);
        //h^2
        hr[2] = mulmod(hr[0], hr[0], _pp);
        // h^3
        hr[3] = mulmod(hr[2], hr[0], _pp);
        // qx = -h^3  -2u1h^2+r^2
        uint256 qx = addmod(mulmod(hr[1], hr[1], _pp), _pp - hr[3], _pp);
        qx = addmod(qx, _pp - mulmod(2, mulmod(zs[0], hr[2], _pp), _pp), _pp);
        // qy = -s1*z1*h^3+r(u1*h^2 -x^3)
        uint256 qy = mulmod(hr[1], addmod(mulmod(zs[0], hr[2], _pp), _pp - qx, _pp), _pp);
        qy = addmod(qy, _pp - mulmod(zs[1], hr[3], _pp), _pp);
        // qz = h*z1*z2
        uint256 qz = mulmod(hr[0], mulmod(_z1, _z2, _pp), _pp);
        return (qx, qy, qz);
    }

    /// @dev Doubles a points (x, y, z).
    /// @param _x coordinate x of P1
    /// @param _y coordinate y of P1
    /// @param _z coordinate z of P1
    /// @param _aa the a scalar in the curve equation
    /// @param _pp the modulus
    /// @return (qx, qy, qz) 2P in Jacobian
    function jacDouble(
        uint256 _x,
        uint256 _y,
        uint256 _z,
        uint256 _aa,
        uint256 _pp)
    internal pure returns (uint256, uint256, uint256)
    {
        if (_z == 0)
            return (_x, _y, _z);

        // We follow the equations described in https://pdfs.semanticscholar.org/5c64/29952e08025a9649c2b0ba32518e9a7fb5c2.pdf Section 5
        // Note: there is a bug in the paper regarding the m parameter, M=3*(x1^2)+a*(z1^4)
        // x, y, z at this point represent the squares of _x, _y, _z
        uint256 x = mulmod(_x, _x, _pp);
        //x1^2
        uint256 y = mulmod(_y, _y, _pp);
        //y1^2
        uint256 z = mulmod(_z, _z, _pp);
        //z1^2

        // s
        uint s = mulmod(4, mulmod(_x, y, _pp), _pp);
        // m
        uint m = addmod(mulmod(3, x, _pp), mulmod(_aa, mulmod(z, z, _pp), _pp), _pp);

        // x, y, z at this point will be reassigned and rather represent qx, qy, qz from the paper
        // This allows to reduce the gas cost and stack footprint of the algorithm
        // qx
        x = addmod(mulmod(m, m, _pp), _pp - addmod(s, s, _pp), _pp);
        // qy = -8*y1^4 + M(S-T)
        y = addmod(mulmod(m, addmod(s, _pp - x, _pp), _pp), _pp - mulmod(8, mulmod(y, y, _pp), _pp), _pp);
        // qz = 2*y1*z1
        z = mulmod(2, mulmod(_y, _z, _pp), _pp);

        return (x, y, z);
    }

    /// @dev Multiply point (x, y, z) times d.
    /// @param _d scalar to multiply
    /// @param _x coordinate x of P1
    /// @param _y coordinate y of P1
    /// @param _z coordinate z of P1
    /// @param _aa constant of curve
    /// @param _pp the modulus
    /// @return (qx, qy, qz) d*P1 in Jacobian
    function jacMul(
        uint256 _d,
        uint256 _x,
        uint256 _y,
        uint256 _z,
        uint256 _aa,
        uint256 _pp)
    internal pure returns (uint256, uint256, uint256)
    {
        // Early return in case that `_d == 0`
        if (_d == 0) {
            return (_x, _y, _z);
        }

        uint256 remaining = _d;
        uint256 qx = 0;
        uint256 qy = 0;
        uint256 qz = 1;

        // Double and add algorithm
        while (remaining != 0) {
            if ((remaining & 1) != 0) {
                (qx, qy, qz) = jacAdd(
                    qx,
                    qy,
                    qz,
                    _x,
                    _y,
                    _z,
                    _pp);
            }
            remaining = remaining / 2;
            (_x, _y, _z) = jacDouble(
                _x,
                _y,
                _z,
                _aa,
                _pp);
        }
        return (qx, qy, qz);
    }
    /**
         * @dev Transform affine coordinates into projective coordinates.
         */
    function toProjectivePoint(uint x0, uint y0) public pure
    returns (uint[3] memory P)
    {
        P[2] = addmod(0, 1, PP);
        P[0] = mulmod(x0, P[2], PP);
        P[1] = mulmod(y0, P[2], PP);
    }

    /**
     * @dev Add two points in affine coordinates and return projective point.
     */
    function addAndReturnProjectivePoint(uint x1, uint y1, uint x2, uint y2) public pure
    returns (uint[3] memory P)
    {
        uint x;
        uint y;
        (x, y) = ecAdd(x1, y1, x2, y2, AA, PP);
        P = toProjectivePoint(x, y);
    }

    function validateSignature(bytes32 message, uint[2] memory rs, uint[2] memory Q) public pure
    returns (bool)
    {
        uint n = NN;
        uint p = PP;

        // To disambiguate between public key solutions, include comment below.
        if (rs[0] == 0 || rs[0] >= n || rs[1] == 0) {// || rs[1] > lowSmax)
            return false;
        }
        if (!isOnCurve(Q[0], Q[1])) {
            return false;
        }

        uint x1;
        uint x2;
        uint y1;
        uint y2;

        uint sInv = invMod(rs[1], n);
        (x1, y1) = ecMul(mulmod(uint(message), sInv, NN), GX, GY);
        (x2, y2) = ecMul(mulmod(rs[0], sInv, n), Q[0], Q[1]);
        uint[3] memory P = addAndReturnProjectivePoint(x1, y1, x2, y2);

        if (P[2] == 0) {
            return false;
        }

        uint Px = invMod(P[2], p);
        Px = mulmod(P[0], mulmod(Px, Px, p), p);

        return Px % NN == rs[0];
    }
}