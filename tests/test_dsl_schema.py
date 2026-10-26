from dataclasses import asdict

from unbolt.dsl import Dsl, FieldNode


def test_field_node_and_dsl_round_trip_through_asdict():
    balance = FieldNode(
        name="ACCOUNT-BALANCE",
        level=5,
        pic="S9(7)V99",
        usage="DISPLAY",
        signed=True,
        sign_separate=False,
        digits=9,
        scale=2,
        byte_size=9,
        occurs=None,
        redefines=None,
        value=None,
        source_line=3,
        offset=0,
    )
    record = FieldNode(
        name="CUSTOMER-RECORD",
        level=1,
        pic=None,
        usage="DISPLAY",
        signed=False,
        sign_separate=False,
        digits=0,
        scale=0,
        byte_size=9,
        occurs=None,
        redefines=None,
        value=None,
        source_line=1,
        offset=0,
        children=(balance,),
    )
    dsl = Dsl(version="0", source_file="flat_display.cpy", roots=(record,))

    as_dict = asdict(dsl)

    assert as_dict["version"] == "0"
    assert as_dict["roots"][0]["children"][0]["name"] == "ACCOUNT-BALANCE"
    assert as_dict["roots"][0]["children"][0]["byte_size"] == 9
