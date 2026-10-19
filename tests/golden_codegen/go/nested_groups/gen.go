package generated

import (
	"fmt"
)


type OrderDate struct {
	OrderYear int16
	OrderMonth int8
	OrderDay int8
}

type OrderHeader struct {
	OrderId int32
	OrderDate OrderDate
}

type OrderRecord struct {
	OrderHeader OrderHeader
	OrderTotal int64
}

func ValidateOrderId(v int32) error {
	if v < 0 || v > 99999999 {
		return fmt.Errorf("ORDER-ID: %v outside 0..99999999", v)
	}
	return nil
}

func ValidateOrderYear(v int16) error {
	if v < 0 || v > 9999 {
		return fmt.Errorf("ORDER-YEAR: %v outside 0..9999", v)
	}
	return nil
}

func ValidateOrderMonth(v int8) error {
	if v < 0 || v > 99 {
		return fmt.Errorf("ORDER-MONTH: %v outside 0..99", v)
	}
	return nil
}

func ValidateOrderDay(v int8) error {
	if v < 0 || v > 99 {
		return fmt.Errorf("ORDER-DAY: %v outside 0..99", v)
	}
	return nil
}

func ValidateOrderTotal(v int64) error {
	if v < -999999999 || v > 999999999 {
		return fmt.Errorf("ORDER-TOTAL: %v outside -999999999..999999999", v)
	}
	return nil
}
