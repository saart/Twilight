from client.utils import xor_by_ecdh


def test_enclave_output():
    res = xor_by_ecdh(
        bytes.fromhex("5B6747BF24E1BCDC2BE439BF10000A31A4A73702"),
        123,
        bytes.fromhex("227388F5D3401B01D9D337D70A1FA520139177B643EEA94C9BE94C116BEF324D42EFED09836876CCB86C9348FCB8915FDE016FB452A876549585569D2ED68387")
    )
    assert int.from_bytes(res, "little") in (0, 10)
