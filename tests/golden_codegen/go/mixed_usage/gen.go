package generated

import (
	"fmt"
	"math/big"
)


type FinancialRecord struct {
	RecordId int32
	TransactionCount int32
	UnitPrice int64
	LargeId int64
	HugeValue big.Int
	SensorReading float32
	PreciseReading float64
}

func ValidateRecordId(v int32) error {
	if v < 0 || v > 99999 {
		return fmt.Errorf("RECORD-ID: %v outside 0..99999", v)
	}
	return nil
}

func ValidateTransactionCount(v int32) error {
	if v < -999999999 || v > 999999999 {
		return fmt.Errorf("TRANSACTION-COUNT: %v outside -999999999..999999999", v)
	}
	return nil
}

func ValidateUnitPrice(v int64) error {
	if v < -99999999999 || v > 99999999999 {
		return fmt.Errorf("UNIT-PRICE: %v outside -99999999999..99999999999", v)
	}
	return nil
}

func ValidateLargeId(v int64) error {
	if v < -999999999999999999 || v > 999999999999999999 {
		return fmt.Errorf("LARGE-ID: %v outside -999999999999999999..999999999999999999", v)
	}
	return nil
}
