// Hand-written protobuf message types matching nexum.proto.
// Uses protowire for manual marshal/unmarshal to avoid protoc dependency.

package proto

import (
	"google.golang.org/protobuf/encoding/protowire"
)

// ---- Helper functions ----

func appendString(b []byte, num protowire.Number, s string) []byte {
	if s == "" {
		return b
	}
	b = protowire.AppendTag(b, num, protowire.BytesType)
	b = protowire.AppendString(b, s)
	return b
}

func appendBool(b []byte, num protowire.Number, v bool) []byte {
	if !v {
		return b
	}
	b = protowire.AppendTag(b, num, protowire.VarintType)
	b = protowire.AppendVarint(b, 1)
	return b
}

func appendInt32(b []byte, num protowire.Number, v int32) []byte {
	if v == 0 {
		return b
	}
	b = protowire.AppendTag(b, num, protowire.VarintType)
	b = protowire.AppendVarint(b, uint64(v))
	return b
}

func consumeField(b []byte) (protowire.Number, protowire.Type, int) {
	num, typ, n := protowire.ConsumeTag(b)
	if n < 0 {
		return 0, 0, n
	}
	return num, typ, n
}

func skipField(b []byte, typ protowire.Type) int {
	switch typ {
	case protowire.VarintType:
		_, n := protowire.ConsumeVarint(b)
		return n
	case protowire.Fixed32Type:
		_, n := protowire.ConsumeFixed32(b)
		return n
	case protowire.Fixed64Type:
		_, n := protowire.ConsumeFixed64(b)
		return n
	case protowire.BytesType:
		_, n := protowire.ConsumeBytes(b)
		return n
	case protowire.StartGroupType:
		_, n := protowire.ConsumeGroup(protowire.Number(0), b)
		return n
	default:
		return -1
	}
}

// ---- WorkflowIR ----

type WorkflowIR struct {
	WorkflowId  string
	VersionHash string
	IrJson      string
}

func (m *WorkflowIR) MarshalBinary() ([]byte, error) {
	var b []byte
	b = appendString(b, 1, m.WorkflowId)
	b = appendString(b, 2, m.VersionHash)
	b = appendString(b, 3, m.IrJson)
	return b, nil
}

func (m *WorkflowIR) UnmarshalBinary(data []byte) error {
	for len(data) > 0 {
		num, typ, n := consumeField(data)
		if n < 0 {
			return protowire.ParseError(n)
		}
		data = data[n:]
		switch num {
		case 1:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.WorkflowId = s
			data = data[n:]
		case 2:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.VersionHash = s
			data = data[n:]
		case 3:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.IrJson = s
			data = data[n:]
		default:
			n := skipField(data, typ)
			if n < 0 {
				return protowire.ParseError(n)
			}
			data = data[n:]
		}
	}
	return nil
}

// ---- AckResponse ----

type AckResponse struct {
	Ok            bool
	Compatibility string
	Message       string
}

func (m *AckResponse) MarshalBinary() ([]byte, error) {
	var b []byte
	b = appendBool(b, 1, m.Ok)
	b = appendString(b, 2, m.Compatibility)
	b = appendString(b, 3, m.Message)
	return b, nil
}

func (m *AckResponse) UnmarshalBinary(data []byte) error {
	for len(data) > 0 {
		num, typ, n := consumeField(data)
		if n < 0 {
			return protowire.ParseError(n)
		}
		data = data[n:]
		switch num {
		case 1:
			v, n := protowire.ConsumeVarint(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.Ok = v != 0
			data = data[n:]
		case 2:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.Compatibility = s
			data = data[n:]
		case 3:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.Message = s
			data = data[n:]
		default:
			n := skipField(data, typ)
			if n < 0 {
				return protowire.ParseError(n)
			}
			data = data[n:]
		}
	}
	return nil
}

// ---- ListRequest ----

type ListRequest struct {
	WorkflowId string
	Status     string
	Limit      int32
}

func (m *ListRequest) MarshalBinary() ([]byte, error) {
	var b []byte
	b = appendString(b, 1, m.WorkflowId)
	b = appendString(b, 2, m.Status)
	b = appendInt32(b, 3, m.Limit)
	return b, nil
}

func (m *ListRequest) UnmarshalBinary(data []byte) error {
	for len(data) > 0 {
		num, typ, n := consumeField(data)
		if n < 0 {
			return protowire.ParseError(n)
		}
		data = data[n:]
		switch num {
		case 1:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.WorkflowId = s
			data = data[n:]
		case 2:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.Status = s
			data = data[n:]
		case 3:
			v, n := protowire.ConsumeVarint(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.Limit = int32(v)
			data = data[n:]
		default:
			n := skipField(data, typ)
			if n < 0 {
				return protowire.ParseError(n)
			}
			data = data[n:]
		}
	}
	return nil
}

// ---- ExecutionSummary ----

type ExecutionSummary struct {
	ExecutionId string
	WorkflowId  string
	VersionHash string
	Status      string
	CreatedAt   string
}

func (m *ExecutionSummary) MarshalBinary() ([]byte, error) {
	var b []byte
	b = appendString(b, 1, m.ExecutionId)
	b = appendString(b, 2, m.WorkflowId)
	b = appendString(b, 3, m.VersionHash)
	b = appendString(b, 4, m.Status)
	b = appendString(b, 5, m.CreatedAt)
	return b, nil
}

func (m *ExecutionSummary) UnmarshalBinary(data []byte) error {
	for len(data) > 0 {
		num, typ, n := consumeField(data)
		if n < 0 {
			return protowire.ParseError(n)
		}
		data = data[n:]
		switch num {
		case 1:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.ExecutionId = s
			data = data[n:]
		case 2:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.WorkflowId = s
			data = data[n:]
		case 3:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.VersionHash = s
			data = data[n:]
		case 4:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.Status = s
			data = data[n:]
		case 5:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.CreatedAt = s
			data = data[n:]
		default:
			n := skipField(data, typ)
			if n < 0 {
				return protowire.ParseError(n)
			}
			data = data[n:]
		}
	}
	return nil
}

// ---- ListResponse ----

type ListResponse struct {
	Executions []*ExecutionSummary
}

func (m *ListResponse) MarshalBinary() ([]byte, error) {
	var b []byte
	for _, e := range m.Executions {
		inner, err := e.MarshalBinary()
		if err != nil {
			return nil, err
		}
		b = protowire.AppendTag(b, 1, protowire.BytesType)
		b = protowire.AppendBytes(b, inner)
	}
	return b, nil
}

func (m *ListResponse) UnmarshalBinary(data []byte) error {
	for len(data) > 0 {
		num, typ, n := consumeField(data)
		if n < 0 {
			return protowire.ParseError(n)
		}
		data = data[n:]
		switch num {
		case 1:
			bs, n := protowire.ConsumeBytes(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			e := &ExecutionSummary{}
			if err := e.UnmarshalBinary(bs); err != nil {
				return err
			}
			m.Executions = append(m.Executions, e)
			data = data[n:]
		default:
			n := skipField(data, typ)
			if n < 0 {
				return protowire.ParseError(n)
			}
			data = data[n:]
		}
	}
	return nil
}

// ---- CancelRequest ----

type CancelRequest struct {
	ExecutionId string
}

func (m *CancelRequest) MarshalBinary() ([]byte, error) {
	var b []byte
	b = appendString(b, 1, m.ExecutionId)
	return b, nil
}

func (m *CancelRequest) UnmarshalBinary(data []byte) error {
	for len(data) > 0 {
		num, typ, n := consumeField(data)
		if n < 0 {
			return protowire.ParseError(n)
		}
		data = data[n:]
		switch num {
		case 1:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.ExecutionId = s
			data = data[n:]
		default:
			n := skipField(data, typ)
			if n < 0 {
				return protowire.ParseError(n)
			}
			data = data[n:]
		}
	}
	return nil
}

// ---- ListVersionsRequest ----

type ListVersionsRequest struct {
	WorkflowId string
}

func (m *ListVersionsRequest) MarshalBinary() ([]byte, error) {
	var b []byte
	b = appendString(b, 1, m.WorkflowId)
	return b, nil
}

func (m *ListVersionsRequest) UnmarshalBinary(data []byte) error {
	for len(data) > 0 {
		num, typ, n := consumeField(data)
		if n < 0 {
			return protowire.ParseError(n)
		}
		data = data[n:]
		switch num {
		case 1:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.WorkflowId = s
			data = data[n:]
		default:
			n := skipField(data, typ)
			if n < 0 {
				return protowire.ParseError(n)
			}
			data = data[n:]
		}
	}
	return nil
}

// ---- VersionInfo ----

type VersionInfo struct {
	WorkflowId       string
	VersionHash      string
	Compatibility    string
	RegisteredAt     string
	ActiveExecutions int32
}

func (m *VersionInfo) MarshalBinary() ([]byte, error) {
	var b []byte
	b = appendString(b, 1, m.WorkflowId)
	b = appendString(b, 2, m.VersionHash)
	b = appendString(b, 3, m.Compatibility)
	b = appendString(b, 4, m.RegisteredAt)
	b = appendInt32(b, 5, m.ActiveExecutions)
	return b, nil
}

func (m *VersionInfo) UnmarshalBinary(data []byte) error {
	for len(data) > 0 {
		num, typ, n := consumeField(data)
		if n < 0 {
			return protowire.ParseError(n)
		}
		data = data[n:]
		switch num {
		case 1:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.WorkflowId = s
			data = data[n:]
		case 2:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.VersionHash = s
			data = data[n:]
		case 3:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.Compatibility = s
			data = data[n:]
		case 4:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.RegisteredAt = s
			data = data[n:]
		case 5:
			v, n := protowire.ConsumeVarint(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.ActiveExecutions = int32(v)
			data = data[n:]
		default:
			n := skipField(data, typ)
			if n < 0 {
				return protowire.ParseError(n)
			}
			data = data[n:]
		}
	}
	return nil
}

// ---- ListVersionsResponse ----

type ListVersionsResponse struct {
	Versions []*VersionInfo
}

func (m *ListVersionsResponse) MarshalBinary() ([]byte, error) {
	var b []byte
	for _, v := range m.Versions {
		inner, err := v.MarshalBinary()
		if err != nil {
			return nil, err
		}
		b = protowire.AppendTag(b, 1, protowire.BytesType)
		b = protowire.AppendBytes(b, inner)
	}
	return b, nil
}

func (m *ListVersionsResponse) UnmarshalBinary(data []byte) error {
	for len(data) > 0 {
		num, typ, n := consumeField(data)
		if n < 0 {
			return protowire.ParseError(n)
		}
		data = data[n:]
		switch num {
		case 1:
			bs, n := protowire.ConsumeBytes(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			v := &VersionInfo{}
			if err := v.UnmarshalBinary(bs); err != nil {
				return err
			}
			m.Versions = append(m.Versions, v)
			data = data[n:]
		default:
			n := skipField(data, typ)
			if n < 0 {
				return protowire.ParseError(n)
			}
			data = data[n:]
		}
	}
	return nil
}

// ---- ApproveRequest ----

type ApproveRequest struct {
	ExecutionId string
	NodeId      string
	Approver    string
	Comment     string
}

func (m *ApproveRequest) MarshalBinary() ([]byte, error) {
	var b []byte
	b = appendString(b, 1, m.ExecutionId)
	b = appendString(b, 2, m.NodeId)
	b = appendString(b, 3, m.Approver)
	b = appendString(b, 4, m.Comment)
	return b, nil
}

func (m *ApproveRequest) UnmarshalBinary(data []byte) error {
	for len(data) > 0 {
		num, typ, n := consumeField(data)
		if n < 0 {
			return protowire.ParseError(n)
		}
		data = data[n:]
		switch num {
		case 1:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.ExecutionId = s
			data = data[n:]
		case 2:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.NodeId = s
			data = data[n:]
		case 3:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.Approver = s
			data = data[n:]
		case 4:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.Comment = s
			data = data[n:]
		default:
			n := skipField(data, typ)
			if n < 0 {
				return protowire.ParseError(n)
			}
			data = data[n:]
		}
	}
	return nil
}

// ---- RejectRequest ----

type RejectRequest struct {
	ExecutionId string
	NodeId      string
	Approver    string
	Reason      string
}

func (m *RejectRequest) MarshalBinary() ([]byte, error) {
	var b []byte
	b = appendString(b, 1, m.ExecutionId)
	b = appendString(b, 2, m.NodeId)
	b = appendString(b, 3, m.Approver)
	b = appendString(b, 4, m.Reason)
	return b, nil
}

func (m *RejectRequest) UnmarshalBinary(data []byte) error {
	for len(data) > 0 {
		num, typ, n := consumeField(data)
		if n < 0 {
			return protowire.ParseError(n)
		}
		data = data[n:]
		switch num {
		case 1:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.ExecutionId = s
			data = data[n:]
		case 2:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.NodeId = s
			data = data[n:]
		case 3:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.Approver = s
			data = data[n:]
		case 4:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.Reason = s
			data = data[n:]
		default:
			n := skipField(data, typ)
			if n < 0 {
				return protowire.ParseError(n)
			}
			data = data[n:]
		}
	}
	return nil
}

// ---- EmptyRequest ----

type EmptyRequest struct{}

func (m *EmptyRequest) MarshalBinary() ([]byte, error) {
	return nil, nil
}

func (m *EmptyRequest) UnmarshalBinary(data []byte) error {
	return nil
}

// ---- PendingApprovalItem ----

type PendingApprovalItem struct {
	ExecutionId string
	NodeId      string
	WorkflowId  string
	StartedAt   string
}

func (m *PendingApprovalItem) MarshalBinary() ([]byte, error) {
	var b []byte
	b = appendString(b, 1, m.ExecutionId)
	b = appendString(b, 2, m.NodeId)
	b = appendString(b, 3, m.WorkflowId)
	b = appendString(b, 4, m.StartedAt)
	return b, nil
}

func (m *PendingApprovalItem) UnmarshalBinary(data []byte) error {
	for len(data) > 0 {
		num, typ, n := consumeField(data)
		if n < 0 {
			return protowire.ParseError(n)
		}
		data = data[n:]
		switch num {
		case 1:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.ExecutionId = s
			data = data[n:]
		case 2:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.NodeId = s
			data = data[n:]
		case 3:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.WorkflowId = s
			data = data[n:]
		case 4:
			s, n := protowire.ConsumeString(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			m.StartedAt = s
			data = data[n:]
		default:
			n := skipField(data, typ)
			if n < 0 {
				return protowire.ParseError(n)
			}
			data = data[n:]
		}
	}
	return nil
}

// ---- PendingApprovalsResponse ----

type PendingApprovalsResponse struct {
	Items []*PendingApprovalItem
}

func (m *PendingApprovalsResponse) MarshalBinary() ([]byte, error) {
	var b []byte
	for _, item := range m.Items {
		inner, err := item.MarshalBinary()
		if err != nil {
			return nil, err
		}
		b = protowire.AppendTag(b, 1, protowire.BytesType)
		b = protowire.AppendBytes(b, inner)
	}
	return b, nil
}

func (m *PendingApprovalsResponse) UnmarshalBinary(data []byte) error {
	for len(data) > 0 {
		num, typ, n := consumeField(data)
		if n < 0 {
			return protowire.ParseError(n)
		}
		data = data[n:]
		switch num {
		case 1:
			bs, n := protowire.ConsumeBytes(data)
			if n < 0 {
				return protowire.ParseError(n)
			}
			item := &PendingApprovalItem{}
			if err := item.UnmarshalBinary(bs); err != nil {
				return err
			}
			m.Items = append(m.Items, item)
			data = data[n:]
		default:
			n := skipField(data, typ)
			if n < 0 {
				return protowire.ParseError(n)
			}
			data = data[n:]
		}
	}
	return nil
}
