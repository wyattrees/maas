# Copyright 2026 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from maascommon.enums.boot_resources import BootResourceType
from maasservicelayer.builders.interfaces import InterfaceBuilder
from maasservicelayer.builders.switches import SwitchBuilder
from maasservicelayer.context import Context
from maasservicelayer.db.repositories.interfaces import InterfaceRepository
from maasservicelayer.db.repositories.switches import SwitchesRepository
from maasservicelayer.exceptions.catalog import AlreadyExistsException
from maasservicelayer.models.switches import Switch
from tests.fixtures.factories.bootresources import (
    create_test_bootresource_entry,
)
from tests.fixtures.factories.switches import (
    create_test_switch,
    create_test_switch_interface,
)
from tests.maasapiserver.fixtures.db import Fixture
from tests.maasservicelayer.db.repositories.base import RepositoryCommonTests


class TestSwitchesRepository(RepositoryCommonTests[Switch]):
    """Tests for SwitchesRepository database operations."""

    @pytest.fixture
    def repository_instance(
        self, db_connection: AsyncConnection
    ) -> SwitchesRepository:
        return SwitchesRepository(Context(connection=db_connection))

    @pytest.fixture
    async def _setup_test_list(
        self,
        fixture: Fixture,
        num_objects: int,
        repository_instance: SwitchesRepository,
    ) -> list[Switch]:
        switch_ids = [
            await create_test_switch(fixture) for i in range(num_objects)
        ]
        # Fetch actual Switch objects from database
        created_switches = [
            await repository_instance.get_by_id(switch_id)
            for switch_id in switch_ids
        ]
        return [s for s in created_switches if s is not None]

    @pytest.fixture
    async def created_instance(
        self, fixture: Fixture, repository_instance: SwitchesRepository
    ) -> Switch:
        switch_id = await create_test_switch(fixture)
        switch = await repository_instance.get_by_id(switch_id)
        assert switch is not None
        return switch

    @pytest.fixture
    async def instance_builder_model(self) -> type[SwitchBuilder]:
        return SwitchBuilder

    @pytest.fixture
    async def instance_builder(self) -> SwitchBuilder:
        return SwitchBuilder(
            target_image_id=None,
        )

    async def test_create(
        self,
        repository_instance: SwitchesRepository,
        instance_builder: SwitchBuilder,
    ):
        """Test creating a switch."""
        resource = await repository_instance.create(instance_builder)
        assert resource.id > 0
        assert resource.target_image_id is None

    async def test_update_switch(
        self,
        repository_instance: SwitchesRepository,
        created_instance: Switch,
    ) -> None:
        """Test updating a switch."""
        builder = SwitchBuilder(
            target_image_id=1,
        )
        updated = await repository_instance.update_by_id(
            created_instance.id, builder
        )
        assert updated.id == created_instance.id
        assert updated.target_image_id == 1

    async def test_delete_switch(
        self,
        repository_instance: SwitchesRepository,
        created_instance: Switch,
    ) -> None:
        """Test deleting a switch."""
        await repository_instance.delete_by_id(created_instance.id)

        # Verify it's deleted
        result = await repository_instance.get_by_id(created_instance.id)
        assert result is None

    async def test_create_duplicated(
        self,
        db_connection: AsyncConnection,
        fixture: Fixture,
    ) -> None:
        """Test that creating switches with duplicate MAC addresses in interfaces fails."""

        # Create first switch with an interface
        switch1_id = await create_test_switch(fixture, hostname="switch-1")
        await create_test_switch_interface(
            fixture, switch_id=switch1_id, mac_address="00:11:22:33:44:55"
        )

        # Create second switch
        switch2_id = await create_test_switch(fixture, hostname="switch-2")

        # Try to create interface with duplicate MAC address through repository - should fail
        interface_repo = InterfaceRepository(Context(connection=db_connection))
        builder = InterfaceBuilder(
            name="mgmt", mac_address="00:11:22:33:44:55", switch_id=switch2_id
        )
        with pytest.raises(AlreadyExistsException):
            await interface_repo.create(builder)

    async def test_create_many_duplicated(
        self,
        db_connection: AsyncConnection,
        fixture: Fixture,
    ) -> None:
        """Test that creating multiple switches with duplicate MAC addresses in interfaces fails."""
        # Create first switch with an interface
        switch1_id = await create_test_switch(fixture, hostname="switch-1")
        await create_test_switch_interface(
            fixture, switch_id=switch1_id, mac_address="00:11:22:33:44:55"
        )

        # Create second switch
        switch2_id = await create_test_switch(fixture, hostname="switch-2")

        # Try to create multiple interfaces with duplicate MAC address - should fail
        interface_repo = InterfaceRepository(Context(connection=db_connection))

        with pytest.raises(AlreadyExistsException):
            await interface_repo.create_many(
                [
                    InterfaceBuilder(
                        name="eth0",
                        mac_address="aa:bb:cc:dd:ee:ff",
                        switch_id=switch1_id,
                    ),
                    InterfaceBuilder(
                        name="eth0",
                        mac_address="aa:bb:cc:dd:ee:ff",  # Duplicate MAC
                        switch_id=switch2_id,
                    ),
                ]
            )

    async def test_get_with_target_image(
        self,
        fixture: Fixture,
        repository_instance: SwitchesRepository,
    ) -> None:
        boot_resource = await create_test_bootresource_entry(
            fixture,
            rtype=BootResourceType.SYNCED,
            name="onie/sonic",
            architecture="amd64/generic",
        )
        await create_test_switch(
            fixture,
            target_image_id=boot_resource.id,
        )

        switches = await repository_instance.get_with_target_image(1, 1)
        switch = next(
            entry
            for entry in switches.items
            if entry.target_image_id == boot_resource.id
        )

        assert switch.target_image == "onie/sonic"

    async def test_get_with_target_image_no_image(
        self,
        fixture: Fixture,
        repository_instance: SwitchesRepository,
    ) -> None:
        boot_resource = await create_test_bootresource_entry(
            fixture,
            rtype=BootResourceType.SYNCED,
            name="onie/sonic",
            architecture="amd64/generic",
        )
        switch1_id = await create_test_switch(
            fixture,
            target_image_id=boot_resource.id,
        )
        switch2_id = create_test_switch(
            fixture,
            target_image_id=None,
        )

        switches = await repository_instance.get_with_target_image(1, 2)

        assert switches.items[0].id == switch1_id
        assert switches.items[0].target_image == "onie/sonic"
        assert switches.items[1].id == switch2_id
        assert switches.items[1].target_image is None

    async def test_get_one_with_target_image(
        self,
        fixture: Fixture,
        repository_instance: SwitchesRepository,
    ) -> None:
        boot_resource1 = await create_test_bootresource_entry(
            fixture,
            rtype=BootResourceType.SYNCED,
            name="onie/sonic",
            architecture="amd64/generic",
        )
        boot_resource2 = await create_test_bootresource_entry(
            fixture,
            rtype=BootResourceType.SYNCED,
            name="onie/mellanox",
            architecture="amd64/generic",
        )
        switch_id = await create_test_switch(
            fixture,
            target_image_id=boot_resource1.id,
        )
        await create_test_switch(fixture, target_iamge_id=boot_resource2.id)

        switch = await repository_instance.get_one_with_target_image(switch_id)
        assert switch is not None
        assert switch.target_image == "onie/sonic"

    async def test_get_one_with_boot_resource_doesnt_exist(
        self, fixture: Fixture, repository_instance: SwitchesRepository
    ) -> None:
        switch = repository_instance.get_one_with_target_image(999)
        assert switch is None

    async def test_get_one_with_target_image_no_image(
        self,
        fixture: Fixture,
        repository_instance: SwitchesRepository,
    ) -> None:
        switch_id = await create_test_switch(
            fixture,
            target_image_id=None,
        )
        switch = await repository_instance.get_one_with_target_image(switch_id)
        assert switch is not None
        assert switch.target_image is None
        assert switch.target_image_id is None
