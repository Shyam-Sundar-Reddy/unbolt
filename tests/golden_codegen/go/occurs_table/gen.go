package generated

import (
	"fmt"
)


type ItemTable struct {
	ItemSku string
	ItemQty int16
}

type InventoryRecord struct {
	WarehouseId int16
	ItemCount int8
	ItemTable [5]ItemTable
}

func ValidateWarehouseId(v int16) error {
	if v < 0 || v > 9999 {
		return fmt.Errorf("WAREHOUSE-ID: %v outside 0..9999", v)
	}
	return nil
}

func ValidateItemCount(v int8) error {
	if v < 0 || v > 99 {
		return fmt.Errorf("ITEM-COUNT: %v outside 0..99", v)
	}
	return nil
}

func ValidateItemQty(v int16) error {
	if v < 0 || v > 9999 {
		return fmt.Errorf("ITEM-QTY: %v outside 0..9999", v)
	}
	return nil
}
