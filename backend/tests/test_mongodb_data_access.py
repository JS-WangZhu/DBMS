from bson import ObjectId

from app.services.data_access import _build_mongo_runcommand


def test_find_one_converts_shell_object_id_to_bson():
    object_id = "632964ef34c482508439748c"

    command = _build_mongo_runcommand(
        f'db.User.findOne({{ _id: ObjectId("{object_id}") }})'
    )

    assert command == {
        "find": "User",
        "filter": {"_id": ObjectId(object_id)},
        "limit": 1,
    }


def test_read_commands_convert_nested_extended_json_values_to_bson():
    object_id = "632964ef34c482508439748c"

    command = _build_mongo_runcommand(
        f'db.User.aggregate([{{$match: {{owner_id: {{$oid: "{object_id}"}}}}}}])'
    )

    assert command["pipeline"] == [
        {"$match": {"owner_id": ObjectId(object_id)}}
    ]
